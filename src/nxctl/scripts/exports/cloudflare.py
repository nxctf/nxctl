"""Cloudflare Tunnel provider."""

import logging
import subprocess
import time
import re
import psutil
import os
import yaml
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
    """Cloudflare Tunnel provider using TryCloudflare / Quick Tunnels or Named Tunnels.

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

        self.tunnel_name = getattr(config, "cloudflare_tunnel_name", "")
        self.credentials_file = getattr(config, "cloudflare_credentials_file", "")
        self.subdomains = [sub for sub in getattr(config, "cloudflare_subdomains", []) if sub]

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
        if self.tunnel_name and self.credentials_file and self.subdomains:
            # Named Tunnel Mode: single global process for the tunnel
            return (
                "cloudflared" in command
                and "run" in cmdline
                and self.tunnel_name.lower() in command
            )
        else:
            # TryCloudflare (Quick Tunnel) Mode
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

    def _kill_all_named_tunnel_procs(self) -> None:
        """Kill all cloudflared processes running our named tunnel."""
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info["cmdline"]
                if not cmdline:
                    continue
                command = " ".join(cmdline).lower()
                if "cloudflared" in command and "run" in cmdline and self.tunnel_name.lower() in command:
                    self._kill_process_tree(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _spawn_global_tunnel(self, ingress_mappings: list[tuple[str, int]], log_port: int) -> int:
        """Write global config and spawn a single cloudflared process.

        Returns the real PID of the cloudflared process.
        """
        config_path = self.config.tmp_dir / "cloudflare_tunnel_config.yml"
        credentials_path = str(Path(self.credentials_file).expanduser())

        ingress_rules = []
        for hostname, port in ingress_mappings:
            ingress_rules.append({"hostname": hostname, "service": f"http://localhost:{port}"})
        ingress_rules.append({"service": "http_status:404"})

        config_data = {
            "tunnel": self.tunnel_name,
            "credentials-file": credentials_path,
            "ingress": ingress_rules,
        }
        with open(config_path, "w", encoding="utf-8") as cf:
            yaml.dump(config_data, cf, default_flow_style=False)

        log_path = self._get_log_file(log_port)
        log_path.write_text("", encoding="utf-8")
        log_file = open(log_path, "a", encoding="utf-8")

        cmd = [
            "cloudflared", "tunnel",
            "--config", str(config_path),
            "run", self.tunnel_name,
        ]
        logger.info("Spawning cloudflared named tunnel: %s", " ".join(cmd))
        try:
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

        time.sleep(3.0)
        if proc.poll() is not None:
            full_log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
            raise RuntimeError(f"Failed to start cloudflared named tunnel: {full_log}")

        real_pid = proc.pid
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                if "cloudflared" in " ".join(child.cmdline()).lower():
                    real_pid = child.pid
                    break
        except Exception:
            pass

        return real_pid

    def _collect_active_mappings(self, exclude_port: int | None = None) -> list[tuple[str, int]]:
        """Collect (hostname, port) from alive state files."""
        mappings = []
        for state_path in self.state_dir.glob("cloudflare_*.json"):
            try:
                state_data = load_state_file(state_path)
                if not state_data:
                    continue
                port = int(state_data.get("host_port", 0))
                url = state_data.get("public_url", "")
                if port > 0 and url and (exclude_port is None or port != exclude_port):
                    hostname = url.replace("https://", "").replace("http://", "").strip("/")
                    mappings.append((hostname, port))
            except Exception:
                pass
        return mappings

    def _update_all_state_pids(self, new_pid: int) -> None:
        """Update PID in all cloudflare state files."""
        for state_path in self.state_dir.glob("cloudflare_*.json"):
            try:
                state_data = load_state_file(state_path)
                if state_data:
                    state_data["pid"] = new_pid
                    save_state_file(state_path, state_data)
            except Exception:
                pass

    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> ExportResult:
        """Start cloudflare tunnel (named or quick)."""
        if protocol != "http":
            raise RuntimeError(f"Cloudflare only supports HTTP protocol, got {protocol}")

        logger.info(f"Starting cloudflare tunnel for {challenge_name}:{host_port}")

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

        # Check mode: Named Tunnel Mode or Quick Tunnel Mode
        named_mode = bool(self.tunnel_name and self.credentials_file and self.subdomains)

        if named_mode:
            return self._start_named(challenge_name, host_port)
        else:
            return self._start_quick(challenge_name, host_port)

    def _start_named(self, challenge_name: str, host_port: int) -> ExportResult:
        """Start or restart the single global Named Tunnel cloudflared process.

        Cloudflare only allows ONE process per tunnel ID. So every time a new
        challenge is added we: kill old process → rebuild config with ALL
        active mappings → start fresh. Brief ~3s downtime is acceptable.
        """
        # 1. Reuse if this port already has an active mapping
        _, state = self._load_state(host_port)
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_url", ""))
            if state_pid and state_url and self._is_cloudflare_pid(state_pid, host_port):
                logger.info(f"Reusing existing cloudflare named tunnel: {state_url}")
                return ExportResult(url=state_url, pid=state_pid)
            logger.info("Ignoring stale cloudflare named tunnel state for port %s", host_port)
            delete_state_file(self._get_state_file(host_port))
            delete_state_file(self._get_legacy_state_file(host_port))

        # 2. Collect existing active mappings (excluding this port)
        active_mappings = self._collect_active_mappings(exclude_port=host_port)
        active_subdomains = {h for h, _ in active_mappings}

        # 3. Find a free subdomain for the new port
        allocated_subdomain = None
        for sub in self.subdomains:
            hostname = sub.replace("https://", "").replace("http://", "").strip("/")
            if hostname not in active_subdomains:
                allocated_subdomain = hostname
                break

        if not allocated_subdomain:
            raise RuntimeError("No free Cloudflare subdomains available in config!")

        # 4. Add the new mapping
        active_mappings.append((allocated_subdomain, host_port))

        # 5. Kill ALL existing cloudflared processes for this tunnel
        self._kill_all_named_tunnel_procs()
        time.sleep(1.0)

        # 6. Start fresh global process with ALL mappings
        real_pid = self._spawn_global_tunnel(active_mappings, log_port=host_port)

        # 7. Save state for the NEW port
        public_url = f"https://{allocated_subdomain}"
        save_state_file(
            self._get_state_file(host_port),
            {
                "pid": real_pid,
                "public_url": public_url,
                "host_port": host_port,
                "log_file": str(self._get_log_file(host_port)),
                "started_at": int(time.time()),
            },
        )

        # 8. Update PID on ALL existing state files (they share the same process)
        self._update_all_state_pids(real_pid)

        logger.info(f"Cloudflare Named Tunnel started for {challenge_name} on {public_url} (PID {real_pid})")
        return ExportResult(url=public_url, pid=real_pid)

    def _start_quick(self, challenge_name: str, host_port: int) -> ExportResult:
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

        named_mode = bool(self.tunnel_name and self.credentials_file and self.subdomains)

        if not named_mode:
            # Quick mode: just kill the per-port process
            stopped = False
            _, state = self._load_state(host_port)
            if state:
                pid = int(state.get("pid", 0))
                if pid and self._is_cloudflare_pid(pid, host_port):
                    if kill_process(pid):
                        stopped = True
            delete_state_file(self._get_state_file(host_port))
            delete_state_file(self._get_legacy_state_file(host_port))
            return stopped

        # Named mode: kill global process → remove this port → rebuild with remaining
        # 1. Remove state for this port first
        delete_state_file(self._get_state_file(host_port))
        delete_state_file(self._get_legacy_state_file(host_port))

        # 2. Collect remaining active mappings
        remaining_mappings = self._collect_active_mappings(exclude_port=host_port)

        # 3. Kill ALL cloudflared processes for this tunnel
        self._kill_all_named_tunnel_procs()
        time.sleep(1.0)

        # 4. If there are remaining mappings, restart with them
        if remaining_mappings:
            try:
                first_port = remaining_mappings[0][1]
                real_pid = self._spawn_global_tunnel(remaining_mappings, log_port=first_port)
                self._update_all_state_pids(real_pid)
                logger.info(f"Restarted cloudflared with {len(remaining_mappings)} remaining mapping(s)")
            except Exception as exc:
                logger.warning(f"Failed to restart cloudflared after removing {challenge_name}: {exc}")

        return True

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
