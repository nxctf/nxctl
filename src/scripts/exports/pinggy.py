"""Pinggy tunnel provider."""

import logging
import subprocess
import time
import re
from pathlib import Path
from typing import Optional

import os
import psutil
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

        # Determine mode from config
        mode = getattr(self.config, "pinggy_mode", "cli").lower()

        # Safeguard: check for ghost ssh/pinggy processes on this port
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                cmd_str = " ".join(cmdline).lower()
                if ("ssh" in cmd_str or "pinggy" in cmd_str) and f"localhost:{host_port}" in cmd_str:
                    logger.info(f"Found ghost tunnel process (PID {proc.info['pid']}) for port {host_port}, cleaning up...")
                    try:
                        os.kill(proc.info['pid'], 9)
                    except:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if mode == "python":
            logger.info("Using Pinggy Python SDK mode")
            try:
                import pinggy
                # We run this in a separate background process so it survives CLI exit
                # We'll use a small python snippet to start the tunnel
                token_arg = f', token="{self.config.pinggy_token}"' if hasattr(self.config, "pinggy_token") and self.config.pinggy_token else ""
                py_cmd = (
                    f"import pinggy, time, sys; "
                    f"tunnel = pinggy.start_tunnel(forwardto='localhost:{host_port}', type='tcp'{token_arg}); "
                    f"print(f'ENDPOINT:{{tunnel.urls[0]}}', flush=True); "
                    f"tunnel.wait()"
                )

                log_file = self._get_log_file(challenge_name, host_port)
                command = f"nohup python3 -c \"{py_cmd}\" > {log_file} 2>&1 < /dev/null & echo $!"

                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    shell=True,
                    start_new_session=True,
                )

                if proc.stdout is None:
                    raise RuntimeError("Failed to capture python process PID")

                pid = int(proc.stdout.read().strip())
                return self._wait_for_endpoint(challenge_name, host_port, pid, log_file)

            except ImportError:
                logger.warning("pinggy SDK not installed, falling back to CLI")
                mode = "cli"

        if mode == "cli":
            # Check which command to use: pinggy or ssh fallback
            import shutil
            pinggy_path = shutil.which("pinggy")
            ssh_path = shutil.which("ssh")

            use_ssh = False
            if not pinggy_path:
                logger.info("pinggy binary not found, falling back to ssh")
                use_ssh = True
            else:
                # Test if pinggy binary works (to catch Segmentation Faults on Alpine)
                try:
                    test_proc = subprocess.run([pinggy_path, "--version"], capture_output=True, timeout=2)
                    if test_proc.returncode != 0:
                        use_ssh = True
                except:
                    use_ssh = True

            if use_ssh and not ssh_path:
                raise RuntimeError("Neither 'pinggy' nor 'ssh' found. Please install openssh-client.")

            try:
                log_file = self._get_log_file(challenge_name, host_port)
                if use_ssh:
                    logger.info(f"Using SSH fallback for Pinggy tunnel")
                    command = (
                        f"nohup {ssh_path} -p 443 -o StrictHostKeyChecking=no -o ServerAliveInterval=30 "
                        f"-R0:localhost:{host_port} {protocol}@free.pinggy.io "
                        f"> {log_file} 2>&1 < /dev/null & echo $!"
                    )
                else:
                    logger.info(f"Using pinggy binary for tunnel")
                    command = (
                        f"nohup {pinggy_path} -p 443 -R0:localhost:{host_port} {protocol}@free.pinggy.io "
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
                    raise RuntimeError("Failed to capture tunnel PID")

                pid = int(proc.stdout.read().strip())
                return self._wait_for_endpoint(challenge_name, host_port, pid, log_file)

            except Exception as e:
                raise RuntimeError(f"Failed to start Pinggy CLI/SSH: {str(e)}")

    def _wait_for_endpoint(self, challenge_name: str, host_port: int, pid: int, log_file: Path) -> ExportResult:
        """Wait for endpoint to appear in log file."""
        deadline = time.time() + 15
        while time.time() < deadline:
            if log_file.exists():
                content = log_file.read_text(encoding="utf-8", errors="ignore")
                # Look for tcp:// (CLI/SSH) or ENDPOINT: (Python SDK)
                endpoint = self._extract_endpoint(content)
                if not endpoint and "ENDPOINT:" in content:
                    match = re.search(r"ENDPOINT:(tcp://[^\s]+)", content)
                    endpoint = match.group(1).strip() if match else ""

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

            time.sleep(0.5)

        raise RuntimeError(f"Timed out waiting for pinggy endpoint in {log_file}")


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
