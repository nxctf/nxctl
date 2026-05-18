"""Pinggy tunnel provider."""

from contextlib import contextmanager
import errno
import logging
import os
import time
import re
import socket
import subprocess
import psutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.scripts.exports.logs import ExportLogStore
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
        self.state_dir = Path(getattr(config, "exports_dir", Path(config.cache_dir) / "exports"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs = ExportLogStore(config)

    def _get_state_file(self, challenge_name: str, host_port: int = 0) -> Path:
        """Get state file path for a challenge and host port."""
        safe_name = challenge_name.replace("/", "_")
        if host_port:
            return self.state_dir / f"pinggy_{safe_name}_{host_port}.json"
        return self.state_dir / f"pinggy_{safe_name}.json"

    def _get_log_file(self, challenge_name: str, host_port: int) -> Path:
        """Get log file path for a challenge and port."""
        safe_name = challenge_name.replace("/", "_")
        return self.logs.active_path(self.name, safe_name, host_port)

    def _get_attempt_log_file(self, challenge_name: str, host_port: int, attempt: int) -> Path:
        """Get an isolated log path for one start attempt."""
        base = self._get_log_file(challenge_name, host_port)
        stamp = int(time.time() * 1000)
        return base.with_name(f"{base.stem}_{stamp}_attempt{attempt}{base.suffix}")

    @contextmanager
    def _port_lock(self, host_port: int):
        """Cross-process provider lock for one pinggy host port."""
        locks_dir = self.state_dir / "locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        lock_path = locks_dir / f"pinggy_{host_port}.lock"
        timeout = float(getattr(self.config, "export_start_lock_timeout_seconds", 60) or 60)
        stale_after = float(getattr(self.config, "export_start_lock_stale_seconds", 180) or 180)
        deadline = time.time() + timeout
        owned = False

        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(f"{os.getpid()} {int(time.time())}\n")
                owned = True
                break
            except FileExistsError:
                if self._is_stale_lock(lock_path, stale_after):
                    try:
                        lock_path.unlink()
                        continue
                    except OSError:
                        pass
                if time.time() >= deadline:
                    raise RuntimeError(f"Timed out waiting for pinggy:{host_port} provider lock")
                time.sleep(0.2)

        try:
            yield
        finally:
            if owned:
                try:
                    lock_path.unlink()
                except OSError:
                    pass

    def _is_stale_lock(self, lock_path: Path, stale_after: float) -> bool:
        try:
            parts = lock_path.read_text(encoding="utf-8", errors="ignore").strip().split()
            pid = int(parts[0]) if parts else 0
            created_at = float(parts[1]) if len(parts) > 1 else 0.0
        except Exception:
            return True
        if created_at and time.time() - created_at > stale_after:
            return True
        return bool(pid and not is_pid_alive(pid))

    def _is_pinggy_pid(self, pid: int, host_port: int) -> bool:
        """Return True when PID is the pinggy process for this local port."""
        if not (pid > 0 and is_pid_alive(pid)):
            return False
        try:
            proc = psutil.Process(pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
            cmdline = proc.cmdline()
        except Exception:
            return False
        command = " ".join(cmdline).lower()
        return (
            "pinggy" in {Path(part).name.lower() for part in cmdline if part}
            or "tcp@free.pinggy.io" in command
        ) and f"localhost:{host_port}" in command

    def _find_pinggy_pid(self, host_port: int) -> int:
        """Find one running pinggy process for this local port."""
        pids = self._find_pinggy_pids(host_port)
        return pids[0] if pids else 0

    def _find_pinggy_pids(self, host_port: int) -> list[int]:
        """Find all running pinggy processes for this local port."""
        pids = []
        for proc in psutil.process_iter(["pid", "cmdline", "name", "status"]):
            try:
                if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                    continue
                pid = int(proc.info.get("pid") or 0)
                cmdline = proc.info.get("cmdline") or []
                command = " ".join(cmdline).lower()
                name = str(proc.info.get("name") or "").lower()
                if (
                    ("pinggy" in {Path(part).name.lower() for part in cmdline if part} or name == "pinggy" or "tcp@free.pinggy.io" in command)
                    and f"localhost:{host_port}" in command
                ):
                    pids.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue
        return sorted(set(pids))

    def _kill_existing_pinggies(self, host_port: int) -> int:
        """Kill every pinggy process currently serving this local port."""
        pids = self._find_pinggy_pids(host_port)
        if len(pids) > 1:
            logger.warning("Duplicate pinggy processes for port %s detected: %s", host_port, pids)

        killed = 0
        for pid in pids:
            if kill_process(pid):
                killed += 1
        if pids:
            logger.info("Killed %s/%s pinggy process(es) for port %s", killed, len(pids), host_port)
            self._wait_no_pinggy(host_port)
        return killed

    def _wait_no_pinggy(self, host_port: int, timeout: float = 5.0) -> bool:
        """Wait until no non-zombie pinggy process remains for this local port."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._find_pinggy_pids(host_port):
                return True
            time.sleep(0.2)
        remaining = self._find_pinggy_pids(host_port)
        if remaining:
            logger.warning("Pinggy processes still alive for port %s after kill wait: %s", host_port, remaining)
        return not remaining

    def _ensure_single_pinggy(self, host_port: int) -> int:
        """Return the sole pinggy PID for this port, killing duplicates if present."""
        pids = self._find_pinggy_pids(host_port)
        if not pids:
            return 0
        if len(pids) == 1:
            return pids[0]

        logger.warning("Duplicate pinggy processes for port %s detected before accept: %s", host_port, pids)
        self._kill_existing_pinggies(host_port)
        return 0

    def _terminate_attempt_proc(self, proc: subprocess.Popen | None, host_port: int, reason: str) -> None:
        """Terminate the spawned attempt process and wait/reap before retrying."""
        if not proc:
            return
        if proc.poll() is None:
            logger.info("Killing pinggy attempt PID %s for port %s before retry: %s", proc.pid, host_port, reason)
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
            except Exception:
                kill_process(proc.pid)
        else:
            try:
                proc.wait(timeout=0)
            except Exception:
                pass

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
        endpoints = self._extract_endpoints(text)
        return endpoints[-1] if endpoints else ""

    def _extract_endpoints(self, text: str) -> list[str]:
        """Extract unique pinggy TCP endpoints in output order."""
        endpoints = []
        seen = set()
        for match in re.findall(r"tcp://[^\s]+", text or ""):
            endpoint = match.strip()
            if endpoint not in seen:
                seen.add(endpoint)
                endpoints.append(endpoint)
        return endpoints

    def _endpoint_ready(self, endpoint: str, timeout: float) -> tuple[bool, str]:
        """Return True when the announced public TCP endpoint is resolvable.

        A real TCP connect can consume the first challenge connection for some
        TCP CTF services, so the provider only does DNS readiness by default.
        """
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

    def _start_process_once(self, challenge_name: str, host_port: int, attempt: int) -> ExportResult:
        """Start one pinggy process and wait until its endpoint settles."""
        self._kill_existing_pinggies(host_port)
        if not self._wait_no_pinggy(host_port):
            raise RuntimeError(f"existing pinggy process did not exit for port {host_port}")

        log_file = self._get_attempt_log_file(challenge_name, host_port, attempt)
        log_handle = None
        proc = None
        accepted = False
        try:
            try:
                log_handle = open(log_file, "w", encoding="utf-8")
            except OSError as exc:
                if exc.errno != errno.ETXTBSY:
                    raise
                log_file = log_file.with_name(f"{log_file.stem}_{int(time.time() * 1000)}{log_file.suffix}")
                log_handle = open(log_file, "a", encoding="utf-8")
            log_handle.write(f"--- pinggy start {time.strftime('%Y-%m-%d %H:%M:%S')} port={host_port} attempt={attempt} ---\n")
            log_handle.flush()
            proc = subprocess.Popen(
                ["pinggy", "-p", "443", "-T", f"-R0:localhost:{host_port}", "tcp@free.pinggy.io"],
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )

            startup_timeout = float(getattr(self.config, "pinggy_start_timeout_seconds", 30) or 30)
            probe_timeout = float(getattr(self.config, "pinggy_ready_probe_timeout_seconds", 2) or 2)
            stability_seconds = float(getattr(self.config, "pinggy_stability_seconds", 10) or 10)
            deadline = time.time() + startup_timeout
            endpoint = ""
            stable_since = 0.0
            last_error = ""
            start_position = log_handle.tell()

            while time.time() < deadline:
                live_pid = self._ensure_single_pinggy(host_port)
                proc_alive = proc.poll() is None
                tunnel_alive = proc_alive or bool(live_pid)

                try:
                    log_handle.flush()
                except Exception:
                    pass

                if log_file.exists():
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as fh:
                        fh.seek(start_position)
                        content = fh.read()
                    lower_content = content.lower()
                    if "fatal error" in lower_content or "tunnel worker exited" in lower_content:
                        raise RuntimeError(self._summarize_error(content))
                    endpoints = self._extract_endpoints(content)
                    if len(endpoints) > 1:
                        logger.warning(
                            "Duplicate pinggy endpoints detected for %s:%s in one attempt: %s",
                            challenge_name,
                            host_port,
                            endpoints,
                        )
                        self._kill_existing_pinggies(host_port)
                        self.logs.archive(log_file, self.name, challenge_name, host_port, "duplicate")
                        raise RuntimeError(f"multiple pinggy endpoints in one start session: {', '.join(endpoints)}")

                    if endpoints:
                        if endpoints[0] != endpoint:
                            endpoint = endpoints[0]
                            stable_since = 0.0

                        ready, last_error = self._endpoint_ready(endpoint, probe_timeout)
                        if not ready:
                            stable_since = 0.0
                            if not tunnel_alive:
                                raise RuntimeError(
                                    f"pinggy exited before endpoint became reachable: {endpoint}"
                                    + (f" ({last_error})" if last_error else "")
                                )
                            time.sleep(0.5)
                            continue

                        if stable_since <= 0:
                            stable_since = time.time()
                            time.sleep(0.5)
                            continue

                        if time.time() - stable_since < stability_seconds:
                            time.sleep(0.5)
                            continue

                        ready, last_error = self._endpoint_ready(endpoint, probe_timeout)
                        if not ready:
                            stable_since = 0.0
                            time.sleep(0.5)
                            continue

                        final_pid = self._ensure_single_pinggy(host_port)
                        if not final_pid:
                            raise RuntimeError("pinggy endpoint appeared but no unique live process remained")
                        save_state_file(
                            self._get_state_file(challenge_name, host_port),
                            {
                                "pid": final_pid,
                                "public_endpoint": endpoint,
                                "log_file": str(log_file),
                                "challenge_name": challenge_name,
                                "host_port": host_port,
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info("Pinggy endpoint accepted for %s:%s with PID %s: %s", challenge_name, host_port, final_pid, endpoint)
                        accepted = True
                        return ExportResult(url=endpoint, pid=final_pid)

                if not tunnel_alive:
                    time.sleep(0.5)
                    live_pid = self._ensure_single_pinggy(host_port)
                    if live_pid:
                        continue
                    if log_file.exists():
                        with open(log_file, "r", encoding="utf-8", errors="ignore") as fh:
                            fh.seek(start_position)
                            content = fh.read()
                    else:
                        content = ""
                    if endpoint:
                        raise RuntimeError(
                            f"pinggy exited before endpoint became reachable: {endpoint}"
                            + (f" ({last_error})" if last_error else "")
                        )
                    raise RuntimeError(content.strip() or "pinggy exited before returning an endpoint")

                time.sleep(0.2)

            self._kill_existing_pinggies(host_port)
            if endpoint:
                raise RuntimeError(
                    f"Timed out waiting for reachable pinggy endpoint: {endpoint}"
                    + (f" ({last_error})" if last_error else "")
                )
            raise RuntimeError(f"Timed out waiting for pinggy endpoint in {log_file}")
        finally:
            if log_handle:
                try:
                    log_handle.close()
                except Exception:
                    pass
            if not accepted:
                self._terminate_attempt_proc(proc, host_port, "attempt failed")
                self._kill_existing_pinggies(host_port)
                self.logs.archive(log_file, self.name, challenge_name, host_port, f"attempt{attempt}_failed")
            if proc and proc.poll() is not None:
                try:
                    proc.wait(timeout=0)
                except Exception:
                    pass

    def _summarize_error(self, logs: str) -> str:
        for line in reversed((logs or "").splitlines()):
            clean = line.strip()
            if not clean:
                continue
            lower = clean.lower()
            if "fatal error" in lower or "error" in lower:
                return clean
        return (logs or "").strip() or "pinggy exited before returning an endpoint"

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

        with self._port_lock(host_port):
            logger.info(f"Starting pinggy for {challenge_name}:{host_port}")

            # Try to reuse existing tunnel if still alive
            state_path, state = self._load_state(challenge_name, host_port)
            if state:
                state_pid = int(state.get("pid", 0))
                state_url = str(state.get("public_endpoint", ""))

                if state_pid and state_url and self._is_pinggy_pid(state_pid, host_port):
                    live_pid = self._ensure_single_pinggy(host_port)
                    if live_pid == state_pid:
                        logger.info(f"Reusing existing pinggy tunnel: {state_url}")
                        return ExportResult(url=state_url, pid=state_pid)

                logger.info("Ignoring stale pinggy state for %s:%s", challenge_name, host_port)
                self.logs.archive(state.get("log_file") or self._get_log_file(challenge_name, host_port), self.name, challenge_name, host_port, "stale")
                delete_state_file(state_path)
                self._kill_existing_pinggies(host_port)

            existing_pids = self._find_pinggy_pids(host_port)
            if existing_pids:
                logger.info("Killing orphan pinggy process for %s:%s before restart: %s", challenge_name, host_port, existing_pids)
                self._kill_existing_pinggies(host_port)
                self.logs.archive(self._get_log_file(challenge_name, host_port), self.name, challenge_name, host_port, "orphan")

            attempts = int(getattr(self.config, "pinggy_startup_retries", 3) or 3)
            last_error = ""
            self.logs.archive(self._get_log_file(challenge_name, host_port), self.name, challenge_name, host_port, "previous")
            for attempt in range(1, attempts + 1):
                try:
                    return self._start_process_once(challenge_name, host_port, attempt)
                except FileNotFoundError:
                    raise RuntimeError("pinggy not installed. Install from https://pinggy.io/")
                except Exception as exc:
                    last_error = str(exc)
                    logger.info("pinggy attempt %s/%s failed: %s", attempt, attempts, last_error)
                    self._kill_existing_pinggies(host_port)
                    if attempt < attempts:
                        logger.info("Pinggy attempt killed before retry for %s:%s", challenge_name, host_port)
                        time.sleep(1.0)

            self.logs.archive(self._get_log_file(challenge_name, host_port), self.name, challenge_name, host_port, "failed")
            raise RuntimeError(f"Failed to start pinggy after {attempts} attempts: {last_error}")

    def stop(self, challenge_name: str, host_port: int = 0) -> bool:
        """Stop pinggy tunnel."""
        with self._port_lock(host_port):
            logger.info(f"Stopping pinggy for {challenge_name}")

            stopped = False

            state_path, state = self._load_state(challenge_name, host_port)
            if state:
                self.logs.archive(state.get("log_file") or self._get_log_file(challenge_name, host_port), self.name, challenge_name, host_port, "stopped")

            if self._kill_existing_pinggies(host_port):
                stopped = True
                self.logs.archive(self._get_log_file(challenge_name, host_port), self.name, challenge_name, host_port, "orphan")

            delete_state_file(state_path)

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
        live_pid = self._ensure_single_pinggy(host_port)
        if live_pid and endpoint:
            logger.info("Pinggy state PID mismatch for %s:%s; treating as stale", challenge_name, host_port)
        return False
