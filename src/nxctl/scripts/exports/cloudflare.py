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
from nxctl.core.db import get_db_connection, close_db_connection
from nxctl.core.utils import (
    is_pid_alive,
    load_state_file,
    save_state_file,
    delete_state_file,
    kill_process,
)
from nxctl.core.constants import PROTOCOL_HTTP

logger = logging.getLogger(__name__)


class _CloudflareNamedTunnelLock:
    """Cross-process lock for the single Cloudflare named tunnel process."""

    def __init__(self, config):
        self.lock_file = Path(config.locks_dir) / "cloudflare_named_tunnel.lock"
        self.fd = None

    def __enter__(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Acquiring Cloudflare named tunnel lock: %s", self.lock_file)
        self.fd = open(self.lock_file, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt
                self.fd.seek(0)
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX)

            self.fd.seek(0)
            self.fd.truncate()
            self.fd.write(f"pid={os.getpid()}\n")
            self.fd.write(f"acquired_at={int(time.time())}\n")
            self.fd.flush()
            os.fsync(self.fd.fileno())
            logger.info("Acquired Cloudflare named tunnel lock: %s", self.lock_file)
            return self
        except Exception:
            self.fd.close()
            self.fd = None
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.fd:
            return
        try:
            self.fd.seek(0)
            self.fd.truncate()
            self.fd.write(f"pid={os.getpid()}\n")
            self.fd.write(f"released_at={int(time.time())}\n")
            self.fd.flush()
            os.fsync(self.fd.fileno())
            if os.name == "nt":
                import msvcrt
                self.fd.seek(0)
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
        finally:
            self.fd.close()
            self.fd = None


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

    def _named_mode(self) -> bool:
        return bool(self.tunnel_name and self.credentials_file and self.subdomains)

    def _named_lock(self) -> _CloudflareNamedTunnelLock:
        return _CloudflareNamedTunnelLock(self.config)

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

    def _get_global_config_file(self) -> Path:
        return self.config.tmp_dir / "cloudflare_tunnel_config.yml"

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

        if self._named_mode():
            # Named Tunnel Mode: single global process for the tunnel
            return self._is_named_pid_owned(pid)
        else:
            # TryCloudflare (Quick Tunnel) Mode
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

    def _paths_match(self, actual: str, expected: Path) -> bool:
        try:
            return Path(actual).expanduser().resolve() == expected.expanduser().resolve()
        except Exception:
            actual_norm = os.path.normcase(str(Path(actual).expanduser())).replace("\\", "/")
            expected_norm = os.path.normcase(str(expected.expanduser())).replace("\\", "/")
            return actual_norm == expected_norm

    def _path_is_under(self, path: str, parent: Path) -> bool:
        try:
            Path(path).expanduser().resolve().relative_to(parent.expanduser().resolve())
            return True
        except Exception:
            return False

    def _cmdline_matches_named_tunnel(self, cmdline: list[str]) -> bool:
        if not cmdline:
            return False
        parts = [str(part) for part in cmdline if part]
        parts_lower = [part.lower() for part in parts]
        command = " ".join(parts_lower)
        if "cloudflared" not in command:
            return False
        if "run" not in parts_lower:
            return False
        if self.tunnel_name.lower() not in command:
            return False
        if "--url" in parts_lower:
            return False
        if "--config" in parts_lower:
            index = parts_lower.index("--config")
            if index + 1 >= len(parts):
                return False
            if not self._paths_match(parts[index + 1], self._get_global_config_file()):
                return False
        return True

    def _is_named_pid_owned(self, pid: int) -> bool:
        if not (pid > 0 and is_pid_alive(pid)):
            return False
        try:
            return self._cmdline_matches_named_tunnel(psutil.Process(pid).cmdline())
        except Exception:
            return False

    def _state_looks_owned(self, state_path: Path, state: dict) -> bool:
        tunnel_name = str(state.get("tunnel_name") or "")
        if tunnel_name and tunnel_name != self.tunnel_name:
            return False

        config_file = str(state.get("config_file") or "")
        if config_file and not self._paths_match(config_file, self._get_global_config_file()):
            return False

        log_file = str(state.get("log_file") or "")
        if log_file and not self._path_is_under(log_file, self.log_dir):
            return False

        return state_path.parent == self.state_dir

    def _collect_owned_named_tunnel_pids(self) -> list[int]:
        """Return live nxctl-owned named tunnel PIDs from DB/state metadata."""
        pids: set[int] = set()

        for export in self._db_cloudflare_exports(running_only=False):
            pid = int(export.get("pid") or 0)
            if pid and self._is_named_pid_owned(pid):
                pids.add(pid)

        for state_path in self.state_dir.glob("cloudflare_*.json"):
            state = load_state_file(state_path)
            if not state or not self._state_looks_owned(state_path, state):
                continue
            pid = int(state.get("pid") or 0)
            if pid and self._is_named_pid_owned(pid):
                pids.add(pid)

        return sorted(pids)

    def _stop_owned_named_tunnel_processes(
        self,
        pids: list[int] | None = None,
        exclude_pids: set[int] | None = None,
    ) -> int:
        """Stop only recorded nxctl-owned cloudflared named tunnel PIDs."""
        owned_pids = sorted(set(pids if pids is not None else self._collect_owned_named_tunnel_pids()))
        exclude_pids = exclude_pids or set()
        stopped = 0
        for pid in owned_pids:
            if pid in exclude_pids:
                continue
            if not self._is_named_pid_owned(pid):
                logger.info("Skipping Cloudflare PID %s; commandline does not match nxctl named tunnel", pid)
                continue
            logger.info("Stopping nxctl-owned Cloudflare named tunnel PID %s", pid)
            self._kill_process_tree(pid)
            stopped += 1
        if stopped:
            time.sleep(1.0)
        return stopped

    def _hostname_from_url(self, url: str) -> str:
        return str(url or "").replace("https://", "").replace("http://", "").strip("/")

    def _write_global_config(self, ingress_mappings: list[tuple[str, int]]) -> Path:
        config_path = self._get_global_config_file()
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
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as cf:
            yaml.safe_dump(config_data, cf, default_flow_style=False)
        return config_path

    def _config_contains_mapping(self, hostname: str, host_port: int) -> bool:
        config_path = self._get_global_config_file()
        if not config_path.exists():
            return False
        try:
            config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return False

        expected_host = self._hostname_from_url(hostname)
        expected_service = f"http://localhost:{int(host_port)}"
        for rule in config_data.get("ingress") or []:
            if not isinstance(rule, dict):
                continue
            rule_host = self._hostname_from_url(str(rule.get("hostname") or ""))
            rule_service = str(rule.get("service") or "")
            if rule_host == expected_host and rule_service == expected_service:
                return True
        return False

    def _save_pending_mapping_state(self, hostname: str, host_port: int) -> None:
        state_path = self._get_state_file(host_port)
        now = int(time.time())
        save_state_file(
            state_path,
            {
                "pid": 0,
                "public_url": f"https://{hostname}",
                "host_port": host_port,
                "log_file": str(self._get_log_file(host_port)),
                "config_file": str(self._get_global_config_file()),
                "tunnel_name": self.tunnel_name,
                "pending": True,
                "started_at": now,
                "updated_at": now,
            },
        )

    def _spawn_global_tunnel(self, ingress_mappings: list[tuple[str, int]], log_port: int) -> int:
        """Write global config and spawn a single cloudflared process.

        Returns the real PID of the cloudflared process.
        """
        config_path = self._write_global_config(ingress_mappings)

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

    def _db_cloudflare_exports(self, running_only: bool = True, exclude_port: int | None = None) -> list[dict]:
        db_path = Path(getattr(self.config, "db_file", ""))
        if not db_path.exists():
            return []

        conn = get_db_connection(str(db_path))
        cursor = conn.cursor()
        try:
            params: list[object] = [self.name]
            runtime_filter = "AND ri.status = 'running'" if running_only else ""
            port_filter = ""
            if exclude_port is not None:
                port_filter = "AND ce.target_port != ?"
                params.append(exclude_port)

            cursor.execute(f"""
                SELECT ce.id, c.name AS challenge, ri.status AS runtime_status,
                       ce.target_port AS host_port, ce.public_endpoint AS public_url,
                       ce.pid
                FROM challenge_exports ce
                JOIN runtime_instances ri ON ce.runtime_id = ri.id
                JOIN challenges c ON c.id = ri.challenge_id
                WHERE ce.provider = ?
                  AND ce.status = 'active'
                  AND ce.target_port IS NOT NULL
                  {runtime_filter}
                  {port_filter}
                ORDER BY ce.created_at ASC, ce.id ASC
            """, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.debug("Failed reading active Cloudflare exports from DB: %s", exc)
            return []
        finally:
            close_db_connection(conn)

    def _port_has_running_runtime(self, host_port: int) -> bool:
        db_path = Path(getattr(self.config, "db_file", ""))
        if not db_path.exists():
            return False

        conn = get_db_connection(str(db_path))
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 1
                FROM runtime_instances ri
                JOIN challenges c ON c.id = ri.challenge_id
                LEFT JOIN challenge_ports cp
                  ON cp.challenge_id = c.id
                 AND cp.host_port = ?
                WHERE ri.status = 'running'
                  AND (c.service_port = ? OR cp.id IS NOT NULL)
                LIMIT 1
            """, (host_port, host_port))
            return cursor.fetchone() is not None
        except Exception as exc:
            logger.debug("Failed checking Cloudflare runtime for port %s: %s", host_port, exc)
            return False
        finally:
            close_db_connection(conn)

    def _collect_active_mappings(self, exclude_port: int | None = None) -> list[tuple[str, int]]:
        """Collect (hostname, port), preferring active running DB exports."""
        mappings: list[tuple[str, int]] = []
        active_db_by_port: dict[int, str] = {}
        seen_ports: set[int] = set()
        seen_hosts: set[str] = set()

        for export in self._db_cloudflare_exports(running_only=True, exclude_port=exclude_port):
            try:
                port = int(export.get("host_port") or 0)
                hostname = self._hostname_from_url(str(export.get("public_url") or ""))
            except Exception:
                continue
            if not port or not hostname:
                continue
            if port in seen_ports or hostname in seen_hosts:
                continue
            mappings.append((hostname, port))
            active_db_by_port[port] = hostname
            seen_ports.add(port)
            seen_hosts.add(hostname)

        for state_path in self.state_dir.glob("cloudflare_*.json"):
            try:
                state_data = load_state_file(state_path)
                if not state_data:
                    continue
                port = int(state_data.get("host_port", 0))
                hostname = self._hostname_from_url(str(state_data.get("public_url", "")))
                if not port or not hostname or (exclude_port is not None and port == exclude_port):
                    logger.info("Skipping invalid Cloudflare state file: %s", state_path)
                    continue
                if port in seen_ports or hostname in seen_hosts:
                    continue

                pid = int(state_data.get("pid", 0))
                active_db_match = active_db_by_port.get(port) == hostname
                valid_fallback = (
                    active_db_match
                    or (pid and self._is_named_pid_owned(pid))
                    or self._port_has_running_runtime(port)
                )
                if not valid_fallback:
                    logger.info(
                        "Skipping stale Cloudflare state %s for port %s; no active DB export, running runtime, or live owned PID",
                        state_path,
                        port,
                    )
                    delete_state_file(state_path)
                    continue

                mappings.append((hostname, port))
                seen_ports.add(port)
                seen_hosts.add(hostname)
            except Exception as exc:
                logger.info("Skipping unreadable Cloudflare state %s: %s", state_path, exc)
        return mappings

    def _sync_mapping_states(self, mappings: list[tuple[str, int]], new_pid: int, log_port: int) -> None:
        """Update state metadata for every mapping served by the global process."""
        now = int(time.time())
        log_file = str(self._get_log_file(log_port))
        config_file = str(self._get_global_config_file())
        for hostname, port in mappings:
            state_path = self._get_state_file(port)
            try:
                state_data = load_state_file(state_path)
                state_data.update({
                    "pid": new_pid,
                    "public_url": f"https://{hostname}",
                    "host_port": port,
                    "log_file": log_file,
                    "config_file": config_file,
                    "tunnel_name": self.tunnel_name,
                    "pending": False,
                    "started_at": now,
                    "updated_at": now,
                })
                save_state_file(state_path, state_data)
            except Exception as exc:
                logger.debug("Failed updating Cloudflare state %s: %s", state_path, exc)

    def _update_active_db_pids(self, new_pid: int, ports: set[int] | None = None) -> None:
        """Update active running Cloudflare DB exports to the current global PID."""
        db_path = Path(getattr(self.config, "db_file", ""))
        if not db_path.exists():
            return

        conn = get_db_connection(str(db_path))
        cursor = conn.cursor()
        try:
            params: list[object] = [new_pid, self.name]
            port_filter = ""
            if ports is not None:
                if not ports:
                    return
                placeholders = ",".join("?" for _ in ports)
                port_filter = f"AND target_port IN ({placeholders})"
                params.extend(sorted(ports))

            cursor.execute(f"""
                UPDATE challenge_exports
                SET pid = ?
                WHERE provider = ?
                  AND status = 'active'
                  AND runtime_id IN (
                      SELECT id
                      FROM runtime_instances
                      WHERE status = 'running'
                  )
                  {port_filter}
            """, params)
            conn.commit()
        except Exception as exc:
            logger.debug("Failed updating active Cloudflare export PIDs: %s", exc)
        finally:
            close_db_connection(conn)

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
        named_mode = self._named_mode()

        if named_mode:
            return self._start_named(challenge_name, host_port)
        else:
            return self._start_quick(challenge_name, host_port)

    def _start_named(self, challenge_name: str, host_port: int) -> ExportResult:
        """Start or restart the single global Named Tunnel cloudflared process.

        Cloudflare named tunnel state is global to the tunnel, so updates are
        serialized and old processes are stopped only by recorded nxctl-owned PID.
        """
        with self._named_lock():
            # 1. Reuse if this port already has an active mapping.
            _, state = self._load_state(host_port)
            if state:
                state_pid = int(state.get("pid", 0))
                state_url = str(state.get("public_url", ""))
                state_hostname = self._hostname_from_url(state_url)
                if (
                    state_pid
                    and state_url
                    and self._is_cloudflare_pid(state_pid, host_port)
                    and self._config_contains_mapping(state_hostname, host_port)
                ):
                    logger.info(f"Reusing existing cloudflare named tunnel: {state_url}")
                    return ExportResult(url=state_url, pid=state_pid)
                if state_pid and state_url:
                    logger.info(
                        "Ignoring Cloudflare state for port %s because PID/config mapping is not current",
                        host_port,
                    )
                logger.info("Ignoring stale cloudflare named tunnel state for port %s", host_port)
                delete_state_file(self._get_state_file(host_port))
                delete_state_file(self._get_legacy_state_file(host_port))

            for export in self._db_cloudflare_exports(running_only=True):
                export_port = int(export.get("host_port") or 0)
                export_pid = int(export.get("pid") or 0)
                export_url = str(export.get("public_url") or "")
                hostname = self._hostname_from_url(export_url)
                if (
                    export_port == host_port
                    and export_pid
                    and export_url
                    and self._is_named_pid_owned(export_pid)
                    and self._config_contains_mapping(hostname, host_port)
                ):
                    self._sync_mapping_states([(hostname, host_port)], export_pid, host_port)
                    logger.info(f"Reusing existing cloudflare named tunnel from DB: {export_url}")
                    return ExportResult(url=export_url, pid=export_pid)

            # 2. Collect existing active mappings (excluding this port).
            previous_mappings = self._collect_active_mappings(exclude_port=host_port)
            active_subdomains = {h for h, _ in previous_mappings}

            # 3. Find a free subdomain for the new port.
            allocated_subdomain = None
            for sub in self.subdomains:
                hostname = self._hostname_from_url(sub)
                if hostname not in active_subdomains:
                    allocated_subdomain = hostname
                    break

            if not allocated_subdomain:
                raise RuntimeError("No free Cloudflare subdomains available in config!")

            new_mappings = [*previous_mappings, (allocated_subdomain, host_port)]
            previous_pids = self._collect_owned_named_tunnel_pids()

            # Generate the replacement config before stopping the current process.
            self._save_pending_mapping_state(allocated_subdomain, host_port)
            self._write_global_config(new_mappings)
            try:
                self._stop_owned_named_tunnel_processes(previous_pids)
                real_pid = self._spawn_global_tunnel(new_mappings, log_port=host_port)
                self._stop_owned_named_tunnel_processes(exclude_pids={real_pid})
            except Exception as start_exc:
                logger.warning(
                    "Failed to restart Cloudflare named tunnel for %s; attempting rollback: %s",
                    challenge_name,
                    start_exc,
                )
                try:
                    self._stop_owned_named_tunnel_processes()
                    if not previous_mappings:
                        raise RuntimeError("no previous Cloudflare mappings to restore")
                    rollback_port = previous_mappings[0][1]
                    self._write_global_config(previous_mappings)
                    rollback_pid = self._spawn_global_tunnel(previous_mappings, log_port=rollback_port)
                    self._sync_mapping_states(previous_mappings, rollback_pid, rollback_port)
                    self._update_active_db_pids(
                        rollback_pid,
                        ports={port for _, port in previous_mappings},
                    )
                except Exception as rollback_exc:
                    raise RuntimeError(
                        "Failed to restart Cloudflare named tunnel and rollback also failed: "
                        f"restart error: {start_exc}; rollback error: {rollback_exc}"
                    ) from start_exc
                raise RuntimeError(
                    "Failed to restart Cloudflare named tunnel; previous mapping restored: "
                    f"{start_exc}"
                ) from start_exc

            public_url = f"https://{allocated_subdomain}"
            self._sync_mapping_states(new_mappings, real_pid, host_port)
            self._update_active_db_pids(
                real_pid,
                ports={port for _, port in previous_mappings},
            )

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

        named_mode = self._named_mode()

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

        # Named mode: remove one route and restart the global process safely.
        with self._named_lock():
            previous_mappings = self._collect_active_mappings()
            remaining_mappings = [
                (hostname, port)
                for hostname, port in previous_mappings
                if port != host_port
            ]
            previous_pids = self._collect_owned_named_tunnel_pids()

            try:
                if remaining_mappings:
                    self._write_global_config(remaining_mappings)
                self._stop_owned_named_tunnel_processes(previous_pids)
                if remaining_mappings:
                    first_port = remaining_mappings[0][1]
                    real_pid = self._spawn_global_tunnel(remaining_mappings, log_port=first_port)
                    self._stop_owned_named_tunnel_processes(exclude_pids={real_pid})
                    self._sync_mapping_states(remaining_mappings, real_pid, first_port)
                    self._update_active_db_pids(
                        real_pid,
                        ports={port for _, port in remaining_mappings},
                    )
                    logger.info(f"Restarted cloudflared with {len(remaining_mappings)} remaining mapping(s)")
            except Exception as stop_exc:
                logger.warning(
                    "Failed to restart Cloudflare named tunnel after removing %s; attempting rollback: %s",
                    challenge_name,
                    stop_exc,
                )
                try:
                    self._stop_owned_named_tunnel_processes()
                    if not previous_mappings:
                        raise RuntimeError("no previous Cloudflare mappings to restore")
                    rollback_port = previous_mappings[0][1]
                    self._write_global_config(previous_mappings)
                    rollback_pid = self._spawn_global_tunnel(previous_mappings, log_port=rollback_port)
                    self._sync_mapping_states(previous_mappings, rollback_pid, rollback_port)
                    self._update_active_db_pids(
                        rollback_pid,
                        ports={port for _, port in previous_mappings},
                    )
                except Exception as rollback_exc:
                    raise RuntimeError(
                        "Failed to restart Cloudflare named tunnel after stop and rollback also failed: "
                        f"restart error: {stop_exc}; rollback error: {rollback_exc}"
                    ) from stop_exc
                raise RuntimeError(
                    "Failed to restart Cloudflare named tunnel after stop; previous mapping restored: "
                    f"{stop_exc}"
                ) from stop_exc

            delete_state_file(self._get_state_file(host_port))
            delete_state_file(self._get_legacy_state_file(host_port))
            return True

    def is_running(self, challenge_name: str, host_port: int) -> bool:
        """Check if tunnel is running."""
        if self._named_mode():
            with self._named_lock():
                return self._is_running_unlocked(challenge_name, host_port)
        return self._is_running_unlocked(challenge_name, host_port)

    def _is_running_unlocked(self, challenge_name: str, host_port: int) -> bool:
        _, state = self._load_state(host_port)
        if not state:
            return False

        pid = int(state.get("pid", 0))
        url = state.get("public_url", "")

        if not (pid > 0 and bool(url)):
            return False
        return self._is_cloudflare_pid(pid, host_port)
