"""Localtunnel tunnel provider."""

import logging
import subprocess
import time
import re
import psutil
from pathlib import Path

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.scripts.exports.logs import ExportLogStore
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
        self.state_dir = Path(getattr(config, "exports_dir", Path(config.cache_dir) / "exports"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs = ExportLogStore(config)

    def _get_state_file(self, host_port: int) -> Path:
        """Get state file path for a host port."""
        return self.state_dir / f"localtunnel_{host_port}.json"

    def _get_log_file(self, host_port: int) -> Path:
        """Get log file path for a host port."""
        return self.logs.active_path(self.name, "port", host_port)

    def _extract_url(self, text: str) -> str:
        """Extract URL from localtunnel output."""
        urls = self._extract_urls(text)
        return urls[-1] if urls else ""

    def _extract_urls(self, text: str) -> list[str]:
        """Extract unique URLs from localtunnel output in output order."""
        urls = []
        seen = set()
        for match in re.findall(r"https?://\S+", text or ""):
            url = match.strip()
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def _is_localtunnel_pid(self, pid: int, host_port: int) -> bool:
        """Return True when PID is really the lt process for this port."""
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
            "lt" in command
            and "--port" in cmdline
            and str(host_port) in cmdline
        )

    def _find_localtunnel_pids(self, host_port: int) -> list[int]:
        """Find all live localtunnel processes serving this local port."""
        pids = []
        for proc in psutil.process_iter(['pid', 'cmdline', 'status']):
            try:
                if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                    continue
                pid = int(proc.info.get("pid") or 0)
                cmdline = proc.info.get("cmdline") or []
                command = " ".join(cmdline).lower()
                if (
                    pid
                    and "lt" in command
                    and "--port" in cmdline
                    and str(host_port) in cmdline
                ):
                    pids.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue
        return sorted(set(pids))

    def _find_localtunnel_pid(self, host_port: int) -> int:
        """Backward-compatible single-PID lookup."""
        pids = self._find_localtunnel_pids(host_port)
        return pids[0] if pids else 0

    def _kill_existing_localtunnels(self, host_port: int) -> int:
        """Kill every localtunnel process currently serving this local port."""
        pids = self._find_localtunnel_pids(host_port)
        if len(pids) > 1:
            logger.warning("Duplicate localtunnel processes for port %s detected: %s", host_port, pids)

        killed = 0
        for pid in pids:
            if kill_process(pid):
                killed += 1
        if pids:
            logger.info("Killed %s/%s localtunnel process(es) for port %s", killed, len(pids), host_port)
        return killed

    def _ensure_single_localtunnel(self, host_port: int) -> int:
        """Return the sole localtunnel PID for this port, killing duplicates if present."""
        pids = self._find_localtunnel_pids(host_port)
        if not pids:
            return 0
        if len(pids) == 1:
            return pids[0]

        logger.warning("Duplicate localtunnel processes for port %s detected before accept: %s", host_port, pids)
        self._kill_existing_localtunnels(host_port)
        return 0

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

            if state_pid and state_url and self._is_localtunnel_pid(state_pid, host_port):
                live_pid = self._ensure_single_localtunnel(host_port)
                if live_pid == state_pid:
                    logger.info(f"Reusing existing localtunnel from state: {state_url}")
                    return ExportResult(url=state_url, pid=state_pid)
                logger.info("Ignoring localtunnel state for port %s because PID uniqueness check failed", host_port)
            else:
                logger.info("Ignoring stale localtunnel state for port %s", host_port)
            self.logs.archive(state.get("log_file") or self._get_log_file(host_port), self.name, "port", host_port, "stale")
            delete_state_file(self._get_state_file(host_port))

        # Always start from a clean process set for this port. State reuse above is
        # the only path allowed to keep an existing localtunnel process.
        self._kill_existing_localtunnels(host_port)

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
        timeout = int(getattr(self.config, "localtunnel_startup_timeout", 20) or 20)
        attempts = int(getattr(self.config, "localtunnel_startup_retries", 3) or 3)
        stability_seconds = float(getattr(self.config, "localtunnel_stability_seconds", 5) or 5)
        last_error = ""
        self.logs.archive(self._get_log_file(host_port), self.name, "port", host_port, "previous")

        for attempt in range(1, attempts + 1):
            proc = None
            try:
                self._kill_existing_localtunnels(host_port)
                log_path = self._get_log_file(host_port)
                log_file = open(log_path, "a", encoding="utf-8")
                try:
                    log_file.write(f"\n--- localtunnel start {time.strftime('%Y-%m-%d %H:%M:%S')} port={host_port} attempt={attempt} ---\n")
                    log_file.flush()
                    start_position = log_file.tell()
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

                deadline = time.time() + timeout
                public_url = ""
                stable_since = 0.0
                while time.time() < deadline:
                    session_content = ""
                    if log_path.exists():
                        with open(log_path, "r", encoding="utf-8", errors="ignore") as fh:
                            fh.seek(start_position)
                            session_content = fh.read()

                    urls = self._extract_urls(session_content)
                    if len(urls) > 1:
                        last_error = f"multiple localtunnel URLs in one start session: {', '.join(urls)}"
                        logger.warning(last_error)
                        self._kill_existing_localtunnels(host_port)
                        if proc.poll() is None:
                            kill_process(proc.pid)
                        break

                    live_pid = self._ensure_single_localtunnel(host_port)
                    tunnel_alive = proc.poll() is None or bool(live_pid)

                    if urls:
                        if urls[0] != public_url:
                            public_url = urls[0]
                            stable_since = 0.0

                    if public_url:
                        if not tunnel_alive:
                            last_error = "localtunnel exited after printing a URL"
                            logger.info("localtunnel attempt %s/%s failed: %s", attempt, attempts, last_error)
                            break

                        if stable_since <= 0:
                            stable_since = time.time()
                            time.sleep(0.5)
                            continue

                        if time.time() - stable_since < stability_seconds:
                            time.sleep(0.5)
                            continue

                        live_pid = self._ensure_single_localtunnel(host_port)
                        if not live_pid:
                            last_error = "localtunnel URL appeared but no unique live process remained"
                            logger.info("localtunnel attempt %s/%s failed: %s", attempt, attempts, last_error)
                            break

                        save_state_file(
                            self._get_state_file(host_port),
                            {
                                "pid": live_pid,
                                "public_url": public_url,
                                "host_port": host_port,
                                "log_file": str(log_path),
                                "started_at": int(time.time()),
                            }
                        )
                        logger.info(f"Localtunnel started: {public_url}")
                        return ExportResult(url=public_url, pid=live_pid)

                    if not tunnel_alive:
                        time.sleep(0.5)
                        full_log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
                        last_error = full_log.strip() or "localtunnel exited before printing a URL"
                        logger.info("localtunnel attempt %s/%s failed: %s", attempt, attempts, last_error)
                        break

                    time.sleep(0.2)

                else:
                    last_error = f"timed out after {timeout}s waiting for localtunnel URL"
                    if proc and proc.poll() is None:
                        kill_process(proc.pid)
                    logger.info("localtunnel attempt %s/%s failed: %s", attempt, attempts, last_error)

            except Exception as e:
                last_error = str(e)
                if proc and proc.poll() is None:
                    kill_process(proc.pid)
                self._kill_existing_localtunnels(host_port)
                logger.info("localtunnel attempt %s/%s failed: %s", attempt, attempts, last_error)

            if proc and proc.poll() is None:
                kill_process(proc.pid)
            self._kill_existing_localtunnels(host_port)
            time.sleep(0.7)

        self.logs.archive(self._get_log_file(host_port), self.name, "port", host_port, "failed")
        raise RuntimeError(f"Failed to start localtunnel after {attempts} attempts: {last_error}")

    def stop(self, challenge_name: str, host_port: int) -> bool:
        """Stop localtunnel."""
        logger.info(f"Stopping localtunnel for {challenge_name}:{host_port}")

        stopped = False

        # Kill via PID from state if alive, then sweep every matching process.
        state = load_state_file(self._get_state_file(host_port))
        if state:
            pid = int(state.get("pid", 0))
            if pid and self._is_localtunnel_pid(pid, host_port):
                if kill_process(pid):
                    stopped = True
            self.logs.archive(state.get("log_file") or self._get_log_file(host_port), self.name, "port", host_port, "stopped")
        else:
            self.logs.archive(self._get_log_file(host_port), self.name, "port", host_port, "stopped")

        if self._kill_existing_localtunnels(host_port):
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

        if not (pid > 0 and bool(url)):
            return False
        return self._is_localtunnel_pid(pid, host_port)
