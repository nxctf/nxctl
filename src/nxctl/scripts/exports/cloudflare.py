"""Cloudflare Tunnel provider."""

import logging
import subprocess
import time
import re
import psutil
import os
from pathlib import Path

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.core.utils import (
    is_pid_alive,
    load_state_file,
    save_state_file,
    delete_state_file,
    kill_process,
)
from nxctl.core.constants import PROTOCOL_HTTP

logger = logging.getLogger(__name__)


class CloudflareProvider(ExportProvider):
    """Cloudflare Tunnel provider using TryCloudflare / Quick Tunnels.

    Only supports HTTP protocol.
    """

    name = "cloudflare"
    supported_protocols = [PROTOCOL_HTTP]

    def __init__(self, config):
        """Initialize cloudflare provider."""
        super().__init__(config)
        self.state_dir = config.state_dir
        self.log_dir = config.export_logs_dir / self.name
        self.legacy_state_dir = config.legacy_exports_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        """Get state file path for a host port."""
        return self.state_dir / f"cloudflare_{host_port}.json"

    def _get_legacy_state_file(self, host_port: int) -> Path:
        return self.legacy_state_dir / f"cloudflare_{host_port}.json"

    def _get_legacy_state_files(self, host_port: int) -> list[Path]:
        if hasattr(self.config, "legacy_export_state_dirs"):
            return [path / f"cloudflare_{host_port}.json" for path in self.config.legacy_export_state_dirs()]
        return [self._get_legacy_state_file(host_port)]

    def _get_log_file(self, host_port: int) -> Path:
        """Get log file path for a host port."""
        return self.log_dir / f"cloudflare_{host_port}.log"

    def _load_state(self, host_port: int) -> tuple[Path, dict]:
        state_path = self._get_state_file(host_port)
        state = load_state_file(state_path, self._get_legacy_state_files(host_port))
        return state_path, state

    def _extract_url(self, text: str) -> str:
        """Extract trycloudflare URL from cloudflared output."""
        match = re.search(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", text or "")
        return match.group(0).strip() if match else ""

    def _is_cloudflare_pid(self, pid: int, host_port: int) -> bool:
        """Return True when PID is really the cloudflared process for this port."""
        if not (pid > 0 and is_pid_alive(pid)):
            return False
        try:
            cmdline = psutil.Process(pid).cmdline()
        except Exception:
            return False

        command = " ".join(cmdline).lower()
        return (
            "cloudflared" in command
            and "--url" in cmdline
            and str(host_port) in command
        )

    def _kill_process_tree(self, pid: int) -> None:
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    kill_process(child.pid)
                except Exception:
                    pass
        except Exception:
            pass
        kill_process(pid)

    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> ExportResult:
        """Start cloudflare quick tunnel.

        Args:
            challenge_name: Challenge name
            host_port: Host port to expose
            protocol: Must be "http"

        Returns:
            ExportResult containing URL and PID.
        """
        if protocol != "http":
            raise RuntimeError(f"Cloudflare only supports HTTP protocol, got {protocol}")

        logger.info(f"Starting cloudflare tunnel for {challenge_name}:{host_port}")

        # Try to reuse existing tunnel if still alive (from state file)
        _, state = self._load_state(host_port)
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_url", ""))

            if state_pid and state_url and self._is_cloudflare_pid(state_pid, host_port):
                logger.info(f"Reusing existing cloudflare tunnel from state: {state_url}")
                return ExportResult(url=state_url, pid=state_pid)
            logger.info("Ignoring stale cloudflare state for port %s", host_port)
            delete_state_file(self._get_state_file(host_port))
            delete_state_file(self._get_legacy_state_file(host_port))

        # Fallback: check system processes for any 'cloudflared' running on this port
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and "cloudflared" in cmdline[0].lower() and "--url" in cmdline and str(host_port) in " ".join(cmdline):
                    logger.info(f"Found ghost cloudflared process (PID {proc.info['pid']}) for port {host_port}, killing it to clean up...")
                    try:
                        os.kill(proc.info['pid'], 9)
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check if 'cloudflared' CLI is installed
        try:
            result = subprocess.run(
                ["cloudflared", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("cloudflared CLI not found or not working")
        except FileNotFoundError:
            raise RuntimeError("cloudflared not installed. Run setup.sh to install it.")

        # Start cloudflared process. Save logs to find the trycloudflare URL.
        timeout = 25  # cloudflared takes up to 15s to establish connection
        attempts = 3
        last_error = ""

        for attempt in range(1, attempts + 1):
            proc = None
            try:
                log_path = self._get_log_file(host_port)
                log_path.write_text("", encoding="utf-8")
                log_file = open(log_path, "a", encoding="utf-8")
                try:
                    proc = subprocess.Popen(
                        ["cloudflared", "tunnel", "--url", f"http://localhost:{host_port}"],
                        stdin=subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                finally:
                    log_file.close()

                deadline = time.time() + timeout
                position = 0
                while time.time() < deadline:
                    content = ""
                    if log_path.exists():
                        with open(log_path, "r", encoding="utf-8", errors="ignore") as fh:
                            fh.seek(position)
                            content = fh.read()
                            position = fh.tell()

                    public_url = self._extract_url(content)
                    if public_url:
                        real_pid = proc.pid
                        # Resolve real child if necessary
                        try:
                            parent = psutil.Process(proc.pid)
                            children = parent.children(recursive=True)
                            for child in children:
                                child_cmd = " ".join(child.cmdline()).lower()
                                if "cloudflared" in child_cmd:
                                    real_pid = child.pid
                                    break
                        except Exception:
                            pass

                        save_state_file(
                            self._get_state_file(host_port),
                            {
                                "pid": real_pid,
                                "public_url": public_url,
                                "host_port": host_port,
                                "log_file": str(log_path),
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Cloudflare Tunnel started: {public_url} (PID {real_pid})")
                        return ExportResult(url=public_url, pid=real_pid)

                    if proc.poll() is not None:
                        full_log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
                        public_url = self._extract_url(full_log)
                        if public_url:
                            real_pid = proc.pid
                            save_state_file(
                                self._get_state_file(host_port),
                                {
                                    "pid": real_pid,
                                    "public_url": public_url,
                                    "host_port": host_port,
                                    "log_file": str(log_path),
                                    "started_at": int(time.time()),
                                }
                            )
                            logger.info(f"Cloudflare Tunnel started: {public_url} (PID {real_pid})")
                            return ExportResult(url=public_url, pid=real_pid)

                        last_error = full_log.strip() or "cloudflared exited before printing a URL"
                        logger.info("cloudflare attempt %s/%s failed: %s", attempt, attempts, last_error)
                        break

                    time.sleep(0.5)

                else:
                    last_error = f"timed out after {timeout}s waiting for cloudflared URL"
                    if proc and proc.poll() is None:
                        self._kill_process_tree(proc.pid)
                    logger.info("cloudflare attempt %s/%s failed: %s", attempt, attempts, last_error)

            except Exception as e:
                last_error = str(e)
                if proc and proc.poll() is None:
                    self._kill_process_tree(proc.pid)
                logger.info("cloudflare attempt %s/%s failed: %s", attempt, attempts, last_error)

            time.sleep(1.0)

        raise RuntimeError(f"Failed to start cloudflared after {attempts} attempts: {last_error}")

    def stop(self, challenge_name: str, host_port: int) -> bool:
        """Stop cloudflare tunnel."""
        logger.info(f"Stopping cloudflare tunnel for {challenge_name}:{host_port}")

        stopped = False

        # Kill via PID if alive
        _, state = self._load_state(host_port)
        if state:
            pid = int(state.get("pid", 0))
            if pid and self._is_cloudflare_pid(pid, host_port):
                if kill_process(pid):
                    stopped = True

        # Clean up state file
        delete_state_file(self._get_state_file(host_port))
        delete_state_file(self._get_legacy_state_file(host_port))

        return stopped

    def is_running(self, challenge_name: str, host_port: int) -> bool:
        """Check if tunnel is running."""
        _, state = self._load_state(host_port)
        if not state:
            return False

        pid = int(state.get("pid", 0))
        url = state.get("public_url", "")

        if not (pid > 0 and bool(url)):
            return False
        return self._is_cloudflare_pid(pid, host_port)
