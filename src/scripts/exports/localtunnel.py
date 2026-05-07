"""Localtunnel tunnel provider."""

import logging
import subprocess
import time
import re
from pathlib import Path
from typing import Optional

from src.scripts.exports.base import ExportProvider
from src.core.utils import is_pid_alive, load_state_file, save_state_file, delete_state_file, kill_process
from src.core.constants import PROTOCOL_HTTP

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
        self.state_dir = Path(config.cache_dir).parent / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        """Get state file path for a host port."""
        return self.state_dir / f"localtunnel_{host_port}.json"

    def _extract_url(self, text: str) -> str:
        """Extract URL from localtunnel output."""
        match = re.search(r"https?://\S+", text or "")
        return match.group(0).strip() if match else ""

    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> str:
        """Start localtunnel.

        Args:
            challenge_name: Challenge name
            host_port: Host port to expose
            protocol: Must be "http"

        Returns:
            Public URL
        """
        if protocol != "http":
            raise RuntimeError(f"Localtunnel only supports HTTP protocol, got {protocol}")

        logger.info(f"Starting localtunnel for {challenge_name}:{host_port}")

        # Try to reuse existing tunnel if still alive
        state = load_state_file(self._get_state_file(host_port))
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_url", ""))

            if state_pid and state_url and is_pid_alive(state_pid):
                logger.info(f"Reusing existing localtunnel: {state_url}")
                return state_url

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

        # Start localtunnel process
        try:
            proc = subprocess.Popen(
                ["lt", "--port", str(host_port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )

            if proc.stdout is None:
                raise RuntimeError("Failed to read localtunnel output")

            # Read output to get URL
            deadline = time.time() + 10
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        raise RuntimeError("localtunnel process exited without returning a URL")
                    time.sleep(0.1)
                    continue

                public_url = self._extract_url(line)
                if public_url:
                    save_state_file(
                        self._get_state_file(host_port),
                        {
                            "pid": proc.pid,
                            "public_url": public_url,
                            "host_port": host_port,
                            "started_at": int(time.time()),
                        }
                    )
                    logger.info(f"Localtunnel started: {public_url}")
                    return public_url

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

        return pid > 0 and is_pid_alive(pid) and bool(url)
