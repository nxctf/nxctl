"""Bore Tunnel provider."""

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
from nxctl.core.constants import PROTOCOL_HTTP, PROTOCOL_TCP

logger = logging.getLogger(__name__)


class BoreProvider(ExportProvider):
    """Bore Tunnel provider.

    Supports both HTTP and TCP protocols.
    """

    name = "bore"
    supported_protocols = [PROTOCOL_HTTP, PROTOCOL_TCP]

    def __init__(self, config):
        """Initialize bore provider."""
        super().__init__(config)
        self.state_dir = config.state_dir
        self.log_dir = config.export_logs_dir / self.name
        self.legacy_state_dir = config.legacy_exports_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        """Get state file path for a host port."""
        return self.state_dir / f"bore_{host_port}.json"

    def _get_legacy_state_file(self, host_port: int) -> Path:
        return self.legacy_state_dir / f"bore_{host_port}.json"

    def _get_legacy_state_files(self, host_port: int) -> list[Path]:
        if hasattr(self.config, "legacy_export_state_dirs"):
            return [path / f"bore_{host_port}.json" for path in self.config.legacy_export_state_dirs()]
        return [self._get_legacy_state_file(host_port)]

    def _get_log_file(self, host_port: int) -> Path:
        """Get log file path for a host port."""
        return self.log_dir / f"bore_{host_port}.log"

    def _load_state(self, host_port: int) -> tuple[Path, dict]:
        state_path = self._get_state_file(host_port)
        state = load_state_file(state_path, self._get_legacy_state_files(host_port))
        return state_path, state

    def _extract_endpoint(self, text: str, protocol: str) -> tuple[str, int]:
        """Extract host and port from bore output."""
        match_listen = re.search(r"listening at ([a-zA-Z0-9.-]+):(\d+)", text)
        if match_listen:
            host = match_listen.group(1).strip()
            port = int(match_listen.group(2))
            return host, port

        match_port = re.search(r"remote_port=(\d+)", text)
        if match_port:
            server = getattr(self.config, "bore_server", "bore.pub") or "bore.pub"
            return server, int(match_port.group(1))

        return "", 0

    def _is_bore_pid(self, pid: int, host_port: int) -> bool:
        """Return True when PID is really the bore process for this port."""
        if not (pid > 0 and is_pid_alive(pid)):
            return False
        try:
            cmdline = psutil.Process(pid).cmdline()
        except Exception:
            return False

        command = " ".join(cmdline).lower()
        return (
            "bore" in command
            and "local" in cmdline
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
        """Start bore tunnel.

        Args:
            challenge_name: Challenge name
            host_port: Host port to expose
            protocol: "http" or "tcp"

        Returns:
            ExportResult containing URL and PID.
        """
        if protocol not in self.supported_protocols:
            raise RuntimeError(f"Bore only supports HTTP and TCP protocols, got {protocol}")

        logger.info(f"Starting bore tunnel for {challenge_name}:{host_port}")

        # Try to reuse existing tunnel if still alive (from state file)
        _, state = self._load_state(host_port)
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_url", ""))

            if state_pid and state_url and self._is_bore_pid(state_pid, host_port):
                logger.info(f"Reusing existing bore tunnel from state: {state_url}")
                return ExportResult(url=state_url, pid=state_pid)
            logger.info("Ignoring stale bore state for port %s", host_port)
            delete_state_file(self._get_state_file(host_port))
            delete_state_file(self._get_legacy_state_file(host_port))

        # Fallback: check system processes for any 'bore' running on this port
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and "bore" in cmdline[0].lower() and "local" in cmdline and str(host_port) in cmdline:
                    logger.info(f"Found ghost bore process (PID {proc.info['pid']}) for port {host_port}, killing it to clean up...")
                    try:
                        os.kill(proc.info['pid'], 9)
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check if 'bore' CLI is installed
        try:
            result = subprocess.run(
                ["bore", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0 and b"bore" not in result.stdout:
                pass
        except FileNotFoundError:
            raise RuntimeError("bore not installed. Run setup.sh to install it.")

        # Start bore process. Save logs to find the server/port.
        timeout = 15
        attempts = 3
        last_error = ""

        server = getattr(self.config, "bore_server", "bore.pub") or "bore.pub"

        for attempt in range(1, attempts + 1):
            proc = None
            try:
                log_path = self._get_log_file(host_port)
                log_path.write_text("", encoding="utf-8")
                log_file = open(log_path, "a", encoding="utf-8")
                try:
                    cmd = ["bore", "local", str(host_port), "--to", server]
                    proc = subprocess.Popen(
                        cmd,
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

                    host, remote_port = self._extract_endpoint(content, protocol)
                    if remote_port > 0:
                        real_pid = proc.pid
                        try:
                            parent = psutil.Process(proc.pid)
                            children = parent.children(recursive=True)
                            for child in children:
                                child_cmd = " ".join(child.cmdline()).lower()
                                if "bore" in child_cmd:
                                    real_pid = child.pid
                                    break
                        except Exception:
                            pass

                        prefix = "tcp://" if protocol == PROTOCOL_TCP else "http://"
                        public_url = f"{prefix}{host}:{remote_port}"

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
                        logger.info(f"Bore Tunnel started: {public_url} (PID {real_pid})")
                        return ExportResult(url=public_url, pid=real_pid)

                    if proc.poll() is not None:
                        full_log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
                        host, remote_port = self._extract_endpoint(full_log, protocol)
                        if remote_port > 0:
                            real_pid = proc.pid
                            prefix = "tcp://" if protocol == PROTOCOL_TCP else "http://"
                            public_url = f"{prefix}{host}:{remote_port}"
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
                            logger.info(f"Bore Tunnel started: {public_url} (PID {real_pid})")
                            return ExportResult(url=public_url, pid=real_pid)

                        last_error = full_log.strip() or "bore exited before printing remote port"
                        logger.info("bore attempt %s/%s failed: %s", attempt, attempts, last_error)
                        break

                    time.sleep(0.5)

                else:
                    last_error = f"timed out after {timeout}s waiting for bore port"
                    if proc and proc.poll() is None:
                        self._kill_process_tree(proc.pid)
                    logger.info("bore attempt %s/%s failed: %s", attempt, attempts, last_error)

            except Exception as e:
                last_error = str(e)
                if proc and proc.poll() is None:
                    self._kill_process_tree(proc.pid)
                logger.info("bore attempt %s/%s failed: %s", attempt, attempts, last_error)

            time.sleep(1.0)

        raise RuntimeError(f"Failed to start bore after {attempts} attempts: {last_error}")

    def stop(self, challenge_name: str, host_port: int) -> bool:
        """Stop bore tunnel."""
        logger.info(f"Stopping bore tunnel for {challenge_name}:{host_port}")

        stopped = False

        # Kill via PID if alive
        _, state = self._load_state(host_port)
        if state:
            pid = int(state.get("pid", 0))
            if pid and self._is_bore_pid(pid, host_port):
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
        return self._is_bore_pid(pid, host_port)
