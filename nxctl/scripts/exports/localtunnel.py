"""Localtunnel tunnel provider."""

import logging
import subprocess
import time
import re
import psutil
import os
from pathlib import Path

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.core.utils import is_pid_alive, load_state_file, save_state_file, delete_state_file, kill_process
from nxctl.core.constants import PROTOCOL_HTTP

logger = logging.getLogger(__name__)


class LocaltunnelProvider(ExportProvider):
    """Localtunnel provider.

    Only supports HTTP protocol.
    """

    name = "localtunnel"
    supported_protocols = [PROTOCOL_HTTP]

    def __init__(self, config):
        """Initialize localtunnel provider."""
        super().__init__(config)
        self.state_dir = Path(config.cache_dir) / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        """Get state file path for a host port."""
        return self.state_dir / f"localtunnel_{host_port}.json"

    def _get_log_file(self, host_port: int) -> Path:
        """Get log file path for a host port."""
        return self.state_dir / f"localtunnel_{host_port}.log"

    def _extract_url(self, text: str) -> str:
        """Extract URL from localtunnel output."""
        match = re.search(r"https?://\S+", text or "")
        return match.group(0).strip() if match else ""

    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> ExportResult:
        """Start localtunnel.

        Args:
            challenge_name: Challenge name
            host_port: Host port to expose
            protocol: Must be "http"

        Returns:
            ExportResult containing URL and PID.
        """
        if protocol != "http":
            raise RuntimeError(f"Localtunnel only supports HTTP protocol, got {protocol}")

        logger.info(f"Starting localtunnel for {challenge_name}:{host_port}")

        # Try to reuse existing tunnel if still alive (from state file)
        state = load_state_file(self._get_state_file(host_port))
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_url", ""))

            if state_pid and state_url and is_pid_alive(state_pid):
                logger.info(f"Reusing existing localtunnel from state: {state_url}")
                return ExportResult(url=state_url, pid=state_pid)

        # Fallback: check system processes for any 'lt' running on this port
        # This prevents race conditions between CLI and Daemon
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and "node" in cmdline[0].lower() and "lt" in " ".join(cmdline) and "--port" in cmdline and str(host_port) in cmdline:
                    logger.info(f"Found ghost localtunnel process (PID {proc.info['pid']}) for port {host_port}, reusing it if possible...")
                    # We don't have the URL if state file was missing, but we can kill it to be clean
                    # or just let it be and start new. Better: kill and fresh start to ensure we get a URL.
                    try:
                        os.kill(proc.info['pid'], 9)
                    except:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check if 'lt' CLI is installed
        try:
            result = subprocess.run(
                ["lt", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("localtunnel (lt) CLI not found or not working")
        except FileNotFoundError:
            raise RuntimeError("localtunnel (lt) not installed. Run 'npm install -g localtunnel'")

        # Start localtunnel process. Keep stdout/stderr attached to a log file so
        # the detached process does not die later from writing to a closed pipe.
        try:
            log_path = self._get_log_file(host_port)
            log_file = open(log_path, "w", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    ["lt", "--port", str(host_port)],
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
            finally:
                log_file.close()

            # Read the log to get URL
            deadline = time.time() + 10
            position = 0
            while time.time() < deadline:
                if proc.poll() is not None:
                    content = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
                    public_url = self._extract_url(content)
                    if public_url:
                        save_state_file(
                            self._get_state_file(host_port),
                            {
                                "pid": proc.pid,
                                "public_url": public_url,
                                "host_port": host_port,
                                "log_file": str(log_path),
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Localtunnel started: {public_url}")
                        return ExportResult(url=public_url, pid=proc.pid)
                    raise RuntimeError(f"localtunnel process exited without returning a URL: {content.strip()}")

                if log_path.exists():
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as fh:
                        fh.seek(position)
                        content = fh.read()
                        position = fh.tell()

                    public_url = self._extract_url(content)
                    if public_url:
                        save_state_file(
                            self._get_state_file(host_port),
                            {
                                "pid": proc.pid,
                                "public_url": public_url,
                                "host_port": host_port,
                                "log_file": str(log_path),
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Localtunnel started: {public_url}")
                        return ExportResult(url=public_url, pid=proc.pid)

                time.sleep(0.2)

            raise RuntimeError("Timed out waiting for localtunnel URL")

        except Exception as e:
            raise RuntimeError(f"Failed to start localtunnel: {str(e)}")

    def stop(self, challenge_name: str, host_port: int) -> bool:
        """Stop localtunnel."""
        logger.info(f"Stopping localtunnel for {challenge_name}:{host_port}")

        stopped = False

        # Kill via PID if alive
        state = load_state_file(self._get_state_file(host_port))
        if state:
            pid = int(state.get("pid", 0))
            if pid and is_pid_alive(pid):
                if kill_process(pid):
                    stopped = True

        # Clean up state file
        delete_state_file(self._get_state_file(host_port))

        return stopped

    def is_running(self, challenge_name: str, host_port: int) -> bool:
        """Check if tunnel is running."""
        state = load_state_file(self._get_state_file(host_port))
        if not state:
            return False

        pid = int(state.get("pid", 0))
        url = state.get("public_url", "")

        if not (pid > 0 and is_pid_alive(pid) and bool(url)):
            return False

        try:
            proc = psutil.Process(pid)
            cmdline = proc.cmdline()
            command = " ".join(cmdline).lower()
            return "lt" in command and "--port" in cmdline and str(host_port) in cmdline
        except Exception:
            return False
