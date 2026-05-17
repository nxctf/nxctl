"""Pinggy tunnel provider."""

import logging
import time
import re
import subprocess
import psutil
from pathlib import Path
from typing import Optional

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.core.utils import is_pid_alive, load_state_file, save_state_file, delete_state_file, kill_process
from nxctl.core.constants import PROTOCOL_TCP

logger = logging.getLogger(__name__)


class PinggyProvider(ExportProvider):
    """Pinggy tunnel provider.

    Only supports TCP protocol.
    """

    name = "pinggy"
    supported_protocols = [PROTOCOL_TCP]

    def __init__(self, config):
        """Initialize pinggy provider."""
        super().__init__(config)
        self.state_dir = Path(config.cache_dir) / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, challenge_name: str, host_port: int = 0) -> Path:
        """Get state file path for a challenge and host port."""
        safe_name = challenge_name.replace("/", "_")
        if host_port:
            return self.state_dir / f"pinggy_{safe_name}_{host_port}.json"
        return self.state_dir / f"pinggy_{safe_name}.json"

    def _get_log_file(self, challenge_name: str, host_port: int) -> Path:
        """Get log file path for a challenge and port."""
        safe_name = challenge_name.replace("/", "_")
        log_dir = Path("/tmp/pinggy")
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{safe_name}_{host_port}.log"

    def _is_pinggy_pid(self, pid: int, host_port: int) -> bool:
        """Return True when PID is the pinggy process for this local port."""
        if not (pid > 0 and is_pid_alive(pid)):
            return False
        try:
            cmdline = psutil.Process(pid).cmdline()
        except Exception:
            return False
        command = " ".join(cmdline).lower()
        return (
            "pinggy" in {Path(part).name.lower() for part in cmdline if part}
            or "tcp@free.pinggy.io" in command
        ) and f"localhost:{host_port}" in command

    def _load_state(self, challenge_name: str, host_port: int) -> tuple[Path, dict]:
        """Load current state, migrating legacy challenge-only state when possible."""
        state_path = self._get_state_file(challenge_name, host_port)
        state = load_state_file(state_path)
        if state:
            return state_path, state

        legacy_path = self._get_state_file(challenge_name)
        legacy_state = load_state_file(legacy_path)
        if legacy_state and int(legacy_state.get("host_port", 0) or 0) == int(host_port):
            delete_state_file(legacy_path)
            save_state_file(state_path, legacy_state)
            return state_path, legacy_state

        if legacy_state:
            delete_state_file(legacy_path)

        return state_path, {}

    def _extract_endpoint(self, text: str) -> str:
        """Extract pinggy endpoint from output."""
        match = re.search(r"tcp://[^\s]+", text or "")
        return match.group(0).strip() if match else ""

    def start(self, challenge_name: str, host_port: int, protocol: str = "tcp") -> ExportResult:
        """Start pinggy tunnel.

        Args:
            challenge_name: Challenge name
            host_port: Host port to expose
            protocol: Must be "tcp"

        Returns:
            ExportResult containing endpoint and PID.
        """
        if protocol != "tcp":
            raise RuntimeError(f"Pinggy only supports TCP protocol, got {protocol}")

        logger.info(f"Starting pinggy for {challenge_name}:{host_port}")

        # Try to reuse existing tunnel if still alive
        state_path, state = self._load_state(challenge_name, host_port)
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_endpoint", ""))

            if state_pid and state_url and self._is_pinggy_pid(state_pid, host_port):
                logger.info(f"Reusing existing pinggy tunnel: {state_url}")
                return ExportResult(url=state_url, pid=state_pid)
            logger.info("Ignoring stale pinggy state for %s:%s", challenge_name, host_port)
            delete_state_file(state_path)

        # Start pinggy directly and read the endpoint from the log file.
        log_handle = None
        try:
            log_file = self._get_log_file(challenge_name, host_port)
            log_handle = open(log_file, "w", encoding="utf-8")
            proc = subprocess.Popen(
                ["pinggy", "-p", "443", f"-R0:localhost:{host_port}", "tcp@free.pinggy.io"],
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )

            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    log_handle.flush()
                except Exception:
                    pass

                if proc.poll() is not None:
                    content = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else ""
                    raise RuntimeError(content.strip() or "pinggy exited before returning an endpoint")

                if log_file.exists():
                    content = log_file.read_text(encoding="utf-8", errors="ignore")
                    endpoint = self._extract_endpoint(content)
                    if endpoint:
                        try:
                            log_handle.close()
                        except Exception:
                            pass
                        save_state_file(
                            self._get_state_file(challenge_name, host_port),
                            {
                                "pid": proc.pid,
                                "public_endpoint": endpoint,
                                "log_file": str(log_file),
                                "challenge_name": challenge_name,
                                "host_port": host_port,
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Pinggy tunnel started: {endpoint}")
                        return ExportResult(url=endpoint, pid=proc.pid)

                time.sleep(0.2)

            try:
                log_handle.close()
            except Exception:
                pass
            if proc.poll() is None:
                kill_process(proc.pid)
            raise RuntimeError(f"Timed out waiting for pinggy endpoint in {log_file}")

        except FileNotFoundError:
            if log_handle:
                try:
                    log_handle.close()
                except Exception:
                    pass
            raise RuntimeError("pinggy not installed. Install from https://pinggy.io/")
        except Exception as e:
            if log_handle:
                try:
                    log_handle.close()
                except Exception:
                    pass
            raise RuntimeError(f"Failed to start pinggy: {str(e)}")

    def stop(self, challenge_name: str, host_port: int = 0) -> bool:
        """Stop pinggy tunnel."""
        logger.info(f"Stopping pinggy for {challenge_name}")

        stopped = False

        # Kill via PID if alive
        state_path, state = self._load_state(challenge_name, host_port)
        if state:
            pid = int(state.get("pid", 0))
            if pid and self._is_pinggy_pid(pid, host_port):
                if kill_process(pid):
                    stopped = True

        # Clean up state file
        delete_state_file(state_path)

        return stopped

    def is_running(self, challenge_name: str, host_port: int = 0) -> bool:
        """Check if tunnel is running."""
        state_path, state = self._load_state(challenge_name, host_port)
        if not state:
            return False

        pid = int(state.get("pid", 0))
        endpoint = state.get("public_endpoint", "")

        if not (pid > 0 and bool(endpoint)):
            delete_state_file(state_path)
            return False
        return self._is_pinggy_pid(pid, host_port)
