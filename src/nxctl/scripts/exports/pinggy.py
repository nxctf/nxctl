"""Pinggy tunnel provider."""

import logging
import shlex
import time
import re
import socket
import subprocess
import psutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.core.utils import (
    is_pid_alive,
    load_state_file,
    save_state_file,
    delete_state_file,
    kill_process,
    get_export_state_dir,
    get_export_logs_dir,
    safe_runtime_name,
)
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
        self.state_dir = get_export_state_dir(config)
        self.log_dir = get_export_logs_dir(config, self.name)
        self.legacy_state_dir = Path(getattr(config, "exports_dir", Path(config.cache_dir) / "exports"))
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, challenge_name: str, host_port: int = 0) -> Path:
        """Get state file path for a challenge and host port."""
        safe_name = safe_runtime_name(challenge_name)
        if host_port:
            return self.state_dir / f"pinggy_{safe_name}_{host_port}.json"
        return self.state_dir / f"pinggy_{safe_name}.json"

    def _get_legacy_state_file(self, challenge_name: str, host_port: int = 0) -> Path:
        safe_name = safe_runtime_name(challenge_name)
        if host_port:
            return self.legacy_state_dir / f"pinggy_{safe_name}_{host_port}.json"
        return self.legacy_state_dir / f"pinggy_{safe_name}.json"

    def _get_legacy_state_files(self, challenge_name: str, host_port: int = 0) -> list[Path]:
        safe_name = safe_runtime_name(challenge_name)
        filename = f"pinggy_{safe_name}_{host_port}.json" if host_port else f"pinggy_{safe_name}.json"
        if hasattr(self.config, "legacy_export_state_dirs"):
            return [path / filename for path in self.config.legacy_export_state_dirs()]
        return [self._get_legacy_state_file(challenge_name, host_port)]

    def _get_log_file(self, challenge_name: str, host_port: int) -> Path:
        """Get log file path for a challenge and port."""
        safe_name = safe_runtime_name(challenge_name)
        return self.log_dir / f"pinggy_{safe_name}_{host_port}.log"

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
            or "pinggy" in command
            or "pinggy.io" in command
        ) and f"localhost:{host_port}" in command

    def _find_pinggy_pid(self, host_port: int) -> int:
        """Find a running pinggy process for this local port."""
        for proc in psutil.process_iter(["pid", "cmdline", "name"]):
            try:
                pid = int(proc.info.get("pid") or 0)
                cmdline = proc.info.get("cmdline") or []
                command = " ".join(cmdline).lower()
                name = str(proc.info.get("name") or "").lower()
                if (
                    ("pinggy" in {Path(part).name.lower() for part in cmdline if part} or name == "pinggy" or "pinggy" in command or "pinggy.io" in command)
                    and f"localhost:{host_port}" in command
                ):
                    return pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue
        return 0

    def _load_state(self, challenge_name: str, host_port: int) -> tuple[Path, dict]:
        """Load current state, migrating legacy challenge-only state when possible."""
        state_path = self._get_state_file(challenge_name, host_port)
        state = load_state_file(state_path, self._get_legacy_state_files(challenge_name, host_port))
        if state:
            return state_path, state

        legacy_paths = self._get_legacy_state_files(challenge_name)
        legacy_state = load_state_file(legacy_paths[0], legacy_paths[1:], migrate=False)
        if legacy_state and int(legacy_state.get("host_port", 0) or 0) == int(host_port):
            save_state_file(state_path, legacy_state)
            for legacy_path in legacy_paths:
                delete_state_file(legacy_path)
            return state_path, legacy_state

        if legacy_state:
            for legacy_path in legacy_paths:
                delete_state_file(legacy_path)

        return state_path, {}

    def _extract_endpoint(self, text: str) -> str:
        """Extract pinggy endpoint from output."""
        match = re.search(r"tcp://[^\s]+", text or "")
        return match.group(0).strip() if match else ""

    def _looks_fatal(self, text: str) -> bool:
        lower = (text or "").lower()
        return "fatal error" in lower or "tunnel worker exited" in lower

    def _summarize_failure(self, text: str) -> str:
        for line in reversed((text or "").splitlines()):
            clean = line.strip()
            lower = clean.lower()
            if "fatal error" in lower or "error" in lower or "tunnel worker exited" in lower:
                return clean
        return (text or "").strip() or "pinggy exited before returning an endpoint"

    def _endpoint_ready(self, endpoint: str, timeout: float) -> tuple[bool, str]:
        parsed = urlparse(endpoint if "://" in endpoint else f"tcp://{endpoint}")
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False, "invalid tcp endpoint"
        try:
            socket.getaddrinfo(host, port)
            if bool(getattr(self.config, "pinggy_start_probe_connect", False)):
                with socket.create_connection((host, port), timeout=timeout):
                    pass
            return True, ""
        except Exception as exc:
            return False, str(exc)

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

        timeout = int(getattr(self.config, "pinggy_startup_timeout", getattr(self.config, "export_endpoint_check_timeout_seconds", 20)) or 20)
        attempts = int(getattr(self.config, "pinggy_startup_retries", 3) or 3)
        probe_timeout = float(getattr(self.config, "pinggy_ready_probe_timeout_seconds", 2) or 2)
        last_error = ""

        # Try to reuse existing tunnel if still alive
        state_path, state = self._load_state(challenge_name, host_port)
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_endpoint", ""))

            if state_pid and state_url and self._is_pinggy_pid(state_pid, host_port):
                ready, ready_error = self._endpoint_ready(state_url, probe_timeout)
                if ready:
                    logger.info(f"Reusing existing pinggy tunnel: {state_url}")
                    return ExportResult(url=state_url, pid=state_pid)
                logger.info("Ignoring pinggy state with invalid endpoint for %s:%s: %s", challenge_name, host_port, ready_error)
            logger.info("Ignoring stale pinggy state for %s:%s", challenge_name, host_port)
            delete_state_file(state_path)
            delete_state_file(self._get_legacy_state_file(challenge_name, host_port))

        existing_pid = self._find_pinggy_pid(host_port)
        if existing_pid:
            log_file = self._get_log_file(challenge_name, host_port)
            log_text = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else ""
            endpoint = self._extract_endpoint(log_text)
            if endpoint:
                ready, ready_error = self._endpoint_ready(endpoint, probe_timeout)
                if ready:
                    save_state_file(
                        state_path,
                        {
                            "pid": existing_pid,
                            "public_endpoint": endpoint,
                            "log_file": str(log_file),
                            "challenge_name": challenge_name,
                            "host_port": host_port,
                            "started_at": int(time.time()),
                        }
                    )
                    logger.info("Reconciled existing pinggy process for %s:%s: %s", challenge_name, host_port, endpoint)
                    return ExportResult(url=endpoint, pid=existing_pid)
                last_error = f"existing pinggy endpoint is not resolvable: {endpoint} ({ready_error})"
            else:
                last_error = f"existing pinggy process {existing_pid} has not written an endpoint"
            raise RuntimeError(last_error)

        for attempt in range(1, attempts + 1):
            try:
                log_file = self._get_log_file(challenge_name, host_port)
                log_file.write_text("", encoding="utf-8")
                command = (
                    f"nohup pinggy -p 443 -R0:localhost:{int(host_port)} tcp@free.pinggy.io "
                    f"> {shlex.quote(str(log_file))} 2>&1 < /dev/null & echo $!"
                )
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    shell=True,
                    start_new_session=True,
                )
                stdout, _ = proc.communicate(timeout=5)
                pid_output = (stdout or "").strip().splitlines()[-1] if stdout else ""
                pid = int(pid_output) if pid_output.isdigit() else 0
                if pid <= 0:
                    last_error = f"failed to start pinggy background process: {pid_output}"
                    logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)
                    time.sleep(1.0)
                    continue

                deadline = time.time() + timeout
                position = 0
                full_log = ""
                endpoint = ""
                while time.time() < deadline:
                    content = ""
                    if log_file.exists():
                        with open(log_file, "r", encoding="utf-8", errors="ignore") as fh:
                            fh.seek(position)
                            content = fh.read()
                            position = fh.tell()
                            if content:
                                full_log += content

                    if self._looks_fatal(full_log):
                        last_error = self._summarize_failure(full_log)
                        logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)
                        break

                    detected_endpoint = self._extract_endpoint(full_log)
                    if detected_endpoint:
                        endpoint = detected_endpoint
                        ready, ready_error = self._endpoint_ready(endpoint, probe_timeout)
                        if not ready:
                            last_error = f"endpoint not ready: {ready_error}"
                            time.sleep(0.2)
                            continue

                        if not self._is_pinggy_pid(pid, host_port):
                            last_error = f"pinggy PID {pid} exited after printing endpoint: {endpoint}"
                            logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)
                            break

                        save_state_file(
                            self._get_state_file(challenge_name, host_port),
                            {
                                "pid": pid,
                                "public_endpoint": endpoint,
                                "log_file": str(log_file),
                                "challenge_name": challenge_name,
                                "host_port": host_port,
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Pinggy tunnel started: {endpoint} (PID {pid})")
                        return ExportResult(url=endpoint, pid=pid)

                    if not is_pid_alive(pid):
                        full_log = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else ""
                        last_error = self._summarize_failure(full_log)
                        logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)
                        break

                    time.sleep(0.2)

                else:
                    last_error = f"timed out after {timeout}s waiting for pinggy endpoint"
                    logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)

                if pid > 0 and is_pid_alive(pid):
                    if endpoint:
                        break
                    kill_process(pid)
            except Exception as e:
                last_error = str(e)
                logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)

            time.sleep(1.0)

        raise RuntimeError(f"Failed to start pinggy after {attempts} attempts: {last_error}")

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

        orphan_pid = self._find_pinggy_pid(host_port)
        if orphan_pid and kill_process(orphan_pid):
            stopped = True

        # Clean up state file
        delete_state_file(state_path)
        delete_state_file(self._get_legacy_state_file(challenge_name, host_port))

        return stopped

    def is_running(self, challenge_name: str, host_port: int = 0) -> bool:
        """Check if tunnel is running."""
        state_path, state = self._load_state(challenge_name, host_port)
        if not state:
            return bool(self._find_pinggy_pid(host_port))

        pid = int(state.get("pid", 0))
        endpoint = state.get("public_endpoint", "")

        if not (pid > 0 and bool(endpoint)):
            delete_state_file(state_path)
            return False
        if self._is_pinggy_pid(pid, host_port):
            return True
        return bool(self._find_pinggy_pid(host_port))
