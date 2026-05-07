"""Pinggy tunnel provider."""

import logging
import subprocess
import time
import re
from pathlib import Path
from typing import Optional

from src.scripts.exports.base import ExportProvider, ExportResult
from src.core.utils import is_pid_alive, load_state_file, save_state_file, delete_state_file, kill_process
from src.core.constants import PROTOCOL_TCP

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
        self.state_dir = Path(config.cache_dir).parent / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, challenge_name: str) -> Path:
        """Get state file path for a challenge."""
        safe_name = challenge_name.replace("/", "_")
        return self.state_dir / f"pinggy_{safe_name}.json"

    def _get_log_file(self, challenge_name: str, host_port: int) -> Path:
        """Get log file path for a challenge and port."""
        safe_name = challenge_name.replace("/", "_")
        log_dir = Path("/tmp/pinggy")
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{safe_name}_{host_port}.log"

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
        state = load_state_file(self._get_state_file(challenge_name))
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_endpoint", ""))

            if state_pid and state_url and is_pid_alive(state_pid):
                logger.info(f"Reusing existing pinggy tunnel: {state_url}")
                return ExportResult(url=state_url, pid=state_pid)

        # Start pinggy process using nohup and read the endpoint from the log file.
        try:
            log_file = self._get_log_file(challenge_name, host_port)
            command = (
                f"nohup pinggy -p 443 -R0:localhost:{host_port} tcp@free.pinggy.io "
                f"> {log_file} 2>&1 < /dev/null & echo $!"
            )
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                shell=True,
                start_new_session=True,
            )

            if proc.stdout is None:
                raise RuntimeError("Failed to capture pinggy PID")

            pid_output = proc.stdout.read().strip()
            pid = int(pid_output) if pid_output.isdigit() else 0
            if pid <= 0:
                raise RuntimeError(f"Failed to start pinggy background process: {pid_output}")

            deadline = time.time() + 10
            while time.time() < deadline:
                if log_file.exists():
                    content = log_file.read_text(encoding="utf-8", errors="ignore")
                    endpoint = self._extract_endpoint(content)
                    if endpoint:
                        save_state_file(
                            self._get_state_file(challenge_name),
                            {
                                "pid": pid,
                                "public_endpoint": endpoint,
                                "log_file": str(log_file),
                                "challenge_name": challenge_name,
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Pinggy tunnel started: {endpoint}")
                        return ExportResult(url=endpoint, pid=pid)

                time.sleep(0.2)

            raise RuntimeError(f"Timed out waiting for pinggy endpoint in {log_file}")

        except FileNotFoundError:
            raise RuntimeError("pinggy not installed. Install from https://pinggy.io/")
        except Exception as e:
            raise RuntimeError(f"Failed to start pinggy: {str(e)}")

    def stop(self, challenge_name: str, host_port: int = 0) -> bool:
        """Stop pinggy tunnel."""
        logger.info(f"Stopping pinggy for {challenge_name}")

        stopped = False

        # Kill via PID if alive
        state = load_state_file(self._get_state_file(challenge_name))
        if state:
            pid = int(state.get("pid", 0))
            if pid and is_pid_alive(pid):
                if kill_process(pid):
                    stopped = True

        # Clean up state file
        delete_state_file(self._get_state_file(challenge_name))

        return stopped

    def is_running(self, challenge_name: str, host_port: int = 0) -> bool:
        """Check if tunnel is running."""
        state = load_state_file(self._get_state_file(challenge_name))
        if not state:
            return False

        pid = int(state.get("pid", 0))
        endpoint = state.get("public_endpoint", "")

        return pid > 0 and is_pid_alive(pid) and bool(endpoint)
