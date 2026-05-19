"""Export/tunnel management orchestrator."""

import logging
import os
import re
import socket
import time
import warnings
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import urllib.error
import urllib.request

from nxctl.core.db import get_db_connection, close_db_connection
from nxctl.core.constants import (
    EXPORT_PROVIDER_NGROK,
    EXPORT_PROVIDER_LOCALTUNNEL,
    EXPORT_PROVIDER_PINGGY,
    EXPORT_PROVIDER_CLOUDFLARE,
    EXPORT_PROVIDER_BORE,
    EXPORT_PROVIDER_BASE_IP,
    PROTOCOL_TCP,
)

logger = logging.getLogger(__name__)


class ExportManager:
    """Manages tunnel exports for challenges."""

    def __init__(self, config, db_path: str, providers: Optional[Dict[str, Any]] = None):
        """Initialize export manager."""
        self.config = config
        self.db_path = db_path
        if providers is not None:
            self.providers = providers
        else:
            from nxctl.scripts.exports.ngrok import NgrokProvider
            from nxctl.scripts.exports.localtunnel import LocaltunnelProvider
            from nxctl.scripts.exports.pinggy import PinggyProvider
            from nxctl.scripts.exports.cloudflare import CloudflareProvider
            from nxctl.scripts.exports.bore import BoreProvider

            self.providers: Dict[str, Any] = {
                EXPORT_PROVIDER_NGROK: NgrokProvider(config),
                EXPORT_PROVIDER_LOCALTUNNEL: LocaltunnelProvider(config),
                EXPORT_PROVIDER_PINGGY: PinggyProvider(config),
                EXPORT_PROVIDER_CLOUDFLARE: CloudflareProvider(config),
                EXPORT_PROVIDER_BORE: BoreProvider(config),
            }

    def get_provider(self, provider_name: str) -> Optional[Any]:
        """Get a provider by name."""
        return self.providers.get(provider_name)

    def start_export(self, challenge_name: str, host_port: int, protocol: str, provider_name: str) -> str:
        """Start an export with a specific provider.

        Returns:
            Public URL/endpoint
        """
        return self.start_export_details(
            challenge_name,
            host_port,
            protocol,
            provider_name,
        )["url"]

    def start_export_details(self, challenge_name: str, host_port: int, protocol: str, provider_name: str) -> dict:
        """Start an export and return the normalized export record."""
        provider = self.get_provider(provider_name)
        if not provider:
            raise RuntimeError(f"Unknown provider: {provider_name}")

        if not provider.supports_protocol(protocol):
            raise RuntimeError(f"Provider {provider_name} does not support {protocol} protocol")

        # Start the export
        result = provider.start(challenge_name, host_port, protocol)

        # Save to database
        self._save_export_to_db(
            challenge_name,
            provider_name,
            protocol,
            host_port,
            result.url,
            result.pid,
            export_type="tunnel",
        )

        return self._export_dict(
            challenge_name=challenge_name,
            provider=provider_name,
            export_type="tunnel",
            protocol=protocol,
            host_port=host_port,
            endpoint=result.url,
            pid=result.pid,
            status="active",
        )

    def start_direct_export(self, challenge_name: str, host_port: int, protocol: str) -> dict:
        """Record a direct base_ip export when configured."""
        base_ip = self._configured_base_ip()
        if not base_ip:
            raise RuntimeError("base_ip is not configured")

        endpoint = self._direct_endpoint(base_ip, host_port, protocol)

        self._save_export_to_db(
            challenge_name,
            EXPORT_PROVIDER_BASE_IP,
            protocol,
            host_port,
            endpoint,
            pid=None,
            export_type="direct",
        )

        return self._export_dict(
            challenge_name=challenge_name,
            provider=EXPORT_PROVIDER_BASE_IP,
            export_type="direct",
            protocol=protocol,
            host_port=host_port,
            endpoint=endpoint,
            pid=None,
            status="active",
        )

    def start_available_exports(self, challenge_name: str, challenge, default_providers: Optional[list[str]] = None) -> tuple[list[dict], list[dict]]:
        """Start all automatically discoverable exports for a challenge.

        Returns:
            (successful_exports, failed_exports)
        """
        exports: list[dict] = []
        failures: list[dict] = []
        attempted: set[str] = set()
        host_port = int(challenge.service_port)
        protocol = challenge.service_type

        if self._configured_base_ip():
            attempted.add(EXPORT_PROVIDER_BASE_IP)
            try:
                exports.append(self.start_direct_export(challenge_name, host_port, protocol))
            except Exception as exc:
                failures.append(self._failure_dict(EXPORT_PROVIDER_BASE_IP, "direct", exc))

        # Determine prioritized tunnel providers to try
        priority_list = list(default_providers) if default_providers else self.default_providers_for(protocol)

        for provider_name in priority_list:
            if not provider_name or provider_name in attempted:
                continue
            attempted.add(provider_name)
            if not self._provider_enabled(provider_name):
                continue
            if provider_name == EXPORT_PROVIDER_NGROK and not self._ngrok_token_available():
                continue
            try:
                exports.append(
                    self.start_export_details(
                        challenge_name,
                        host_port,
                        protocol,
                        provider_name,
                    )
                )
            except Exception as exc:
                failures.append(self._failure_dict(provider_name, "tunnel", exc))

        if not exports and failures:
            raise RuntimeError("; ".join(f"{f['provider']}: {f['error']}" for f in failures))

        return exports, failures

    def default_providers_for(self, protocol: str) -> list[str]:
        """Return the existing protocol-based default tunnel providers."""
        if protocol == PROTOCOL_TCP:
            return [EXPORT_PROVIDER_PINGGY, EXPORT_PROVIDER_BORE]
        return [EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_CLOUDFLARE, EXPORT_PROVIDER_BORE]

    def stop_export(self, challenge_name: str, provider_name: str, host_port: int = 0) -> bool:
        """Stop an export."""
        if provider_name == EXPORT_PROVIDER_BASE_IP:
            self._mark_export_inactive(challenge_name, provider_name, host_port)
            return True

        provider = self.get_provider(provider_name)
        if not provider:
            raise RuntimeError(f"Unknown provider: {provider_name}")

        # Stop the export
        stopped = provider.stop(challenge_name, host_port)

        # Mark as inactive in database
        self._mark_export_inactive(challenge_name, provider_name, host_port)

        return stopped

    def stop_all_exports(self, challenge_name: str) -> list[dict]:
        """Stop every active export for a challenge."""
        stopped_exports = []
        for export in self.list_exports(challenge_name, check_health=False, latest_only=False):
            provider_name = export["provider"]
            try:
                stopped = self.stop_export(
                    challenge_name,
                    provider_name,
                    int(export.get("port") or 0),
                )
                export["stopped"] = stopped
            except Exception as exc:
                export["stopped"] = False
                export["error"] = str(exc)
                logger.error("Failed stopping %s export for %s: %s", provider_name, challenge_name, exc)
            stopped_exports.append(export)
        return stopped_exports

    def kill_all_tunnel_processes(self) -> int:
        """Kill orphaned ngrok, localtunnel, pinggy, cloudflare, and bore processes."""
        killed = 0

        try:
            import psutil
        except Exception as exc:
            logger.warning("Cannot sweep tunnel processes because psutil is unavailable: %s", exc)
            return killed

        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue

                cmdline = proc.info.get("cmdline") or []
                if not self._is_tunnel_process(proc.info.get("name") or "", cmdline):
                    continue

                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
                killed += 1
                logger.info("Killed tunnel process PID %s: %s", proc.info["pid"], " ".join(cmdline))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as exc:
                logger.warning("Failed killing tunnel process PID %s: %s", proc.info.get("pid"), exc)

        return killed

    def sweep_orphan_tunnel_processes(self, active_exports: Optional[list[dict]] = None) -> int:
        """Kill duplicate/orphan tunnel processes not represented by active export records."""
        try:
            import psutil
        except Exception as exc:
            logger.warning("Cannot sweep orphan tunnel processes because psutil is unavailable: %s", exc)
            return 0

        active_exports = active_exports if active_exports is not None else self.list_exports(check_health=False)
        keep_exports = [
            export
            for export in active_exports
            if export.get("provider") != EXPORT_PROVIDER_BASE_IP
            and int(export.get("pid") or 0) > 0
            and str(export.get("runtime_status") or "running") == "running"
            and str(export.get("status") or "running") in {"active", "running"}
        ]
        keep_pids = {int(export.get("pid") or 0) for export in keep_exports}
        active_keys = {
            (str(export.get("provider") or ""), int(export.get("port") or 0))
            for export in keep_exports
        }
        seen_keys: set[tuple[str, int]] = set()
        killed = 0

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pid = int(proc.info.get("pid") or 0)
                cmdline = proc.info.get("cmdline") or []
                parsed = self._parse_tunnel_process(proc.info.get("name") or "", cmdline)
                if not parsed:
                    continue

                provider, host_port = parsed
                key = (provider, host_port)
                should_keep = pid in keep_pids and key not in seen_keys
                if should_keep:
                    seen_keys.add(key)
                    continue

                if key in active_keys or pid not in keep_pids:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                    killed += 1
                    logger.info("Killed orphan tunnel process PID %s: %s", pid, " ".join(cmdline))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as exc:
                logger.debug("Failed sweeping tunnel process PID %s: %s", proc.info.get("pid"), exc)

        return killed

    def mark_all_exports_inactive(self) -> int:
        """Mark every active export record inactive."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE challenge_exports SET status = 'inactive' WHERE status = 'active'")
            conn.commit()
            return cursor.rowcount
        finally:
            close_db_connection(conn)

    def check_export_alive(self, export: dict) -> bool:
        """Check if an export is actually alive by PID."""
        if export.get("type") == "direct" or export.get("provider") == EXPORT_PROVIDER_BASE_IP:
            return export.get("runtime_status") == "running"

        provider = self.get_provider(export['provider'])
        if not provider:
            return False

        # Apply a 45-second startup grace period during checks to let the tunnel fully register and stabilize
        try:
            if hasattr(provider, "_load_state"):
                if export.get("provider") in {"localtunnel", "cloudflare", "bore"}:
                    _, state = provider._load_state(int(export.get("port") or 0))
                else:
                    _, state = provider._load_state(export.get("challenge") or "", int(export.get("port") or 0))
                if state:
                    started_at = int(state.get("started_at", 0))
                    if started_at > 0 and (time.time() - started_at) < 45:
                        return True
        except Exception:
            pass

        try:
            return bool(provider.is_running(export.get("challenge") or "", int(export.get("port") or 0)))
        except Exception:
            pass

        pid = export.get('pid')
        if not pid:
            return True  # Assume alive if no PID stored (for legacy)

        return provider.is_pid_running(pid)

    def test_tunnel_exports(
        self,
        challenge_name: Optional[str] = None,
        timeout: Optional[float] = None,
        mark_unhealthy: bool = False,
    ) -> list[dict]:
        """Actively test tunnel endpoints, not just provider PIDs."""
        from nxctl.core.utils import is_port_in_use, load_state_file, save_state_file

        timeout = float(
            timeout
            if timeout is not None
            else getattr(self.config, "export_endpoint_check_timeout_seconds", 5) or 5
        )
        exports = [
            export
            for export in self.list_exports(challenge_name, check_health=True)
            if export.get("provider") != EXPORT_PROVIDER_BASE_IP
            and export.get("type") != "direct"
        ]

        results: list[dict] = []
        for export in exports:
            # Check startup grace period (45 seconds) before active liveness check probe
            is_new = False
            try:
                provider = self.get_provider(export.get("provider") or "")
                if (
                    export.get("provider") != EXPORT_PROVIDER_PINGGY
                    and provider
                    and hasattr(provider, "_load_state")
                ):
                    if export.get("provider") in {"localtunnel", "cloudflare", "bore"}:
                        _, state = provider._load_state(int(export.get("port") or 0))
                    else:
                        _, state = provider._load_state(export.get("challenge") or "", int(export.get("port") or 0))
                    if state:
                        started_at = int(state.get("started_at", 0))
                        if started_at > 0 and (time.time() - started_at) < 45:
                            is_new = True
            except Exception:
                pass

            if is_new:
                endpoint = str(export.get("url") or export.get("endpoint") or "").strip()
                if not endpoint:
                    is_new = False

            if is_new:
                # Inside grace period: immediately report Reachable to preserve hostname
                results.append({
                    "challenge": export.get("challenge") or "-",
                    "provider": export.get("provider") or "-",
                    "type": export.get("type") or "-",
                    "port_label": export.get("port_label") or export.get("port") or "-",
                    "reachable": True,
                    "health": "reachable",
                    "latency_ms": 0,
                    "url": endpoint,
                    "error": None,
                })
                continue

            started = time.monotonic()
            ok, error = self._test_export_endpoint(export, timeout)
            latency_ms = int((time.monotonic() - started) * 1000)
            result = dict(export)
            result.update({
                "reachable": ok,
                "health": "reachable" if ok else "unreachable",
                "latency_ms": latency_ms,
                "error": error,
            })
            results.append(result)

            if ok:
                # Clear failure timestamp if it was previously set
                try:
                    provider = self.get_provider(export.get("provider") or "")
                    if provider:
                        if export.get("provider") in {"localtunnel", "cloudflare", "bore"}:
                            state_path = provider._get_state_file(int(export.get("port") or 0))
                        elif export.get("provider") == "pinggy":
                            state_path = provider._get_state_file(export.get("challenge") or "", int(export.get("port") or 0))
                        else:
                            state_path = None

                        if state_path and state_path.exists():
                            state = load_state_file(state_path)
                            if "first_failed_at" in state:
                                del state["first_failed_at"]
                                save_state_file(state_path, state)
                except Exception:
                    pass

            if mark_unhealthy and not ok:
                try:
                    process_alive = self.check_export_alive(export)
                    port_in_use = is_port_in_use(int(export.get("port") or 0))
                    should_recreate = False

                    if not process_alive:
                        logger.info("Export process for %s (%s) is dead, marking unhealthy.", export.get("challenge"), export.get("provider"))
                        should_recreate = True
                    elif not port_in_use:
                        logger.info("Local port %s for %s is not active, marking unhealthy.", export.get("port"), export.get("challenge"))
                        should_recreate = True
                    else:
                        provider = self.get_provider(export.get("provider") or "")
                        if provider:
                            try:
                                if export.get("provider") in {"localtunnel", "cloudflare", "bore"}:
                                    state_path = provider._get_state_file(int(export.get("port") or 0))
                                elif export.get("provider") == "pinggy":
                                    state_path = provider._get_state_file(export.get("challenge") or "", int(export.get("port") or 0))
                                else:
                                    state_path = None

                                if state_path and state_path.exists():
                                    state = load_state_file(state_path)
                                    first_failed = state.get("first_failed_at")
                                    now = int(time.time())

                                    if not first_failed:
                                        state["first_failed_at"] = now
                                        save_state_file(state_path, state)
                                        logger.info("Export %s for %s failed active probe, starting cooldown...", export.get("provider"), export.get("challenge"))
                                    else:
                                        cooldown = int(getattr(self.config, "restart_cooldown_seconds", 300) or 300)
                                        elapsed = now - int(first_failed)
                                        if elapsed >= cooldown:
                                            logger.info("Export %s for %s failed active probe beyond cooldown (%ss), marking unhealthy.", export.get("provider"), export.get("challenge"), elapsed)
                                            should_recreate = True
                                        else:
                                            logger.info("Export %s for %s failed active probe, within cooldown (%ss/%ss). Preserving.", export.get("provider"), export.get("challenge"), elapsed, cooldown)
                                else:
                                    should_recreate = True
                            except Exception as e:
                                logger.warning("Error handling failure cooldown for %s: %s", export.get("challenge"), e)
                                should_recreate = True
                        else:
                            should_recreate = True

                    if should_recreate:
                        self.stop_export(
                            export.get("challenge") or "",
                            export.get("provider") or "",
                            int(export.get("port") or 0),
                        )
                        if export.get("id"):
                            self._mark_id_inactive(int(export["id"]))
                    else:
                        if export.get("provider") != EXPORT_PROVIDER_PINGGY:
                            # Override liveness result to preserve the active status (prevents auto-heal recreation)
                            result["reachable"] = True
                            result["health"] = "reachable (cooldown)"
                            result["error"] = f"unreachable: {error} (preserving)"

                except Exception as exc:
                    logger.warning(
                        "Failed stopping unhealthy %s export for %s: %s",
                        export.get("provider"),
                        export.get("challenge"),
                        exc,
                    )

        return results

    def _test_export_endpoint(self, export: dict, timeout: float) -> tuple[bool, str]:
        endpoint = str(export.get("url") or export.get("endpoint") or "").strip()
        if not endpoint:
            return False, "missing endpoint"

        if export.get("provider") in {EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_CLOUDFLARE}:
            if export.get("status") == "dead":
                return False, "process is not running"
            return self._test_dns_endpoint(endpoint)

        protocol = str(export.get("protocol") or "").lower()
        if endpoint.startswith("tcp://") or protocol == PROTOCOL_TCP:
            return self._test_tcp_endpoint(endpoint, timeout)

        return self._test_http_endpoint(endpoint, timeout)

    def _test_dns_endpoint(self, endpoint: str) -> tuple[bool, str]:
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return False, "invalid endpoint"
        try:
            socket.getaddrinfo(host, port)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _test_http_endpoint(self, endpoint: str, timeout: float) -> tuple[bool, str]:
        try:
            import requests
            try:
                from urllib3.exceptions import InsecureRequestWarning
            except Exception:
                InsecureRequestWarning = Warning

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                response = requests.get(endpoint, timeout=timeout, verify=False)
            body = (response.text or "")[:4096].lower()
            if self._looks_like_tunnel_failure(response.status_code, body):
                return False, f"http {response.status_code}"
            return True, ""
        except ImportError:
            pass
        except Exception as exc:
            return False, str(exc)

        try:
            with urllib.request.urlopen(endpoint, timeout=timeout) as response:
                body = response.read(4096).decode("utf-8", errors="ignore").lower()
                if self._looks_like_tunnel_failure(response.status, body):
                    return False, f"http {response.status}"
                return True, ""
        except urllib.error.HTTPError as exc:
            body = exc.read(4096).decode("utf-8", errors="ignore").lower()
            if self._looks_like_tunnel_failure(exc.code, body):
                return False, f"http {exc.code}"
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _looks_like_tunnel_failure(self, status_code: int, body: str) -> bool:
        if status_code in {502, 503, 504}:
            return True
        failure_markers = (
            "err_ngrok_3200",
            "endpoint is offline",
            "tunnel not found",
            "failed to connect to upstream",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
        )
        return any(marker in body for marker in failure_markers)

    def _test_tcp_endpoint(self, endpoint: str, timeout: float) -> tuple[bool, str]:
        parsed = urlparse(endpoint if "://" in endpoint else f"tcp://{endpoint}")
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False, "invalid tcp endpoint"

        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, ""
        except Exception as exc:
            return False, str(exc)

    def list_exports(
        self,
        challenge_name: Optional[str] = None,
        check_health: bool = True,
        latest_only: bool = True,
        dedupe: bool = True,
    ) -> list:
        """List all active exports."""
        if dedupe:
            self.dedupe_active_exports()
        self._deactivate_direct_exports_if_unconfigured()
        self._backfill_direct_exports(challenge_name)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            latest_clause = ""
            if latest_only:
                latest_clause = """
                    AND ri.id = (
                        SELECT id
                        FROM runtime_instances
                        WHERE challenge_id = c.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    )
                """

            if challenge_name:
                cursor.execute(f"""
                    SELECT ce.id, c.name, ri.status AS runtime_status, cp.internal_port,
                           ce.provider, ce.export_type, ce.protocol, ce.target_port,
                           ce.public_endpoint, ce.pid, ce.status, ce.created_at
                    FROM challenge_exports ce
                    JOIN runtime_instances ri ON ce.runtime_id = ri.id
                    JOIN challenges c ON c.id = ri.challenge_id
                    LEFT JOIN challenge_ports cp
                      ON cp.challenge_id = c.id
                     AND cp.host_port = ce.target_port
                    WHERE c.name = ? AND ce.status = 'active'
                    {latest_clause}
                    ORDER BY CASE WHEN ce.provider = 'base_ip' THEN 0 ELSE 1 END, ce.created_at ASC
                """, (challenge_name,))
            else:
                cursor.execute(f"""
                    SELECT ce.id, c.name, ri.status AS runtime_status, cp.internal_port,
                           ce.provider, ce.export_type, ce.protocol, ce.target_port,
                           ce.public_endpoint, ce.pid, ce.status, ce.created_at
                    FROM challenge_exports ce
                    JOIN runtime_instances ri ON ce.runtime_id = ri.id
                    JOIN challenges c ON c.id = ri.challenge_id
                    LEFT JOIN challenge_ports cp
                      ON cp.challenge_id = c.id
                     AND cp.host_port = ce.target_port
                    WHERE ce.status = 'active'
                    {latest_clause}
                    ORDER BY c.name ASC, CASE WHEN ce.provider = 'base_ip' THEN 0 ELSE 1 END, ce.created_at ASC
                """)

            exports = []
            seen_exports: set[tuple[str, str, int]] = set()
            for row in cursor.fetchall():
                if row["provider"] == EXPORT_PROVIDER_BASE_IP and not self._configured_base_ip():
                    continue

                export_key = (
                    str(row["name"]),
                    str(row["provider"]),
                    int(row["target_port"] or 0),
                )
                if export_key in seen_exports:
                    self._mark_id_inactive(int(row["id"]))
                    continue
                seen_exports.add(export_key)

                export_data = {
                    'id': row['id'],
                    'challenge': row['name'],
                    'id': row['id'],
                    'runtime_status': row['runtime_status'],
                    'internal_port': row['internal_port'],
                    'port_label': f"{row['target_port']}:{row['internal_port']}" if row['internal_port'] else str(row['target_port']),
                    'created_at': row['created_at'],
                } | self._export_dict(
                    challenge_name=row['name'],
                    provider=row['provider'],
                    export_type=row['export_type'] or "tunnel",
                    protocol=row['protocol'],
                    host_port=row['target_port'],
                    endpoint=row['public_endpoint'],
                    pid=row['pid'],
                    status=row['status'],
                )

                if check_health:
                    alive = self.check_export_alive(export_data)
                    if not alive:
                        export_data['status'] = 'dead'
                        # Optional: auto-mark as inactive in DB if dead
                        # self._mark_id_inactive(row['id'])

                exports.append(export_data)

            return exports

        finally:
            close_db_connection(conn)

    def reconcile_exports(self) -> int:
        """Check active exports and mark dead/stopped-runtime records inactive."""
        dead_count = self.dedupe_active_exports()
        exports = self.list_exports(check_health=True, latest_only=False)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            for export in exports:
                if export.get("runtime_status") != "running":
                    if export.get("provider") != EXPORT_PROVIDER_BASE_IP:
                        try:
                            provider = self.get_provider(export["provider"])
                            if provider:
                                provider.stop(
                                    export.get("challenge") or "",
                                    int(export.get("port") or 0),
                                )
                        except Exception as exc:
                            logger.warning(
                                "Failed stopping orphaned %s export for %s: %s",
                                export.get("provider"),
                                export.get("challenge"),
                                exc,
                            )
                    cursor.execute("UPDATE challenge_exports SET status = 'inactive' WHERE id = ?", (export['id'],))
                    dead_count += 1
                elif export['status'] == 'dead':
                    cursor.execute("UPDATE challenge_exports SET status = 'inactive' WHERE id = ?", (export['id'],))
                    dead_count += 1

            conn.commit()
        finally:
            close_db_connection(conn)

        active_exports = self.list_exports(check_health=False, latest_only=False)
        dead_count += self.sweep_orphan_tunnel_processes(active_exports)
        return dead_count

    def prune_inactive(self, provider_name: Optional[str] = None) -> int:
        """Delete inactive export records."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            if provider_name:
                cursor.execute(
                    "DELETE FROM challenge_exports WHERE status != 'active' AND provider = ?",
                    (provider_name,)
                )
            else:
                cursor.execute("DELETE FROM challenge_exports WHERE status != 'active'")

            conn.commit()
            return cursor.rowcount

        finally:
            close_db_connection(conn)

    def _save_export_to_db(self, challenge_name: str, provider: str, protocol: str, host_port: int, public_endpoint: str, pid: Optional[int] = None, export_type: str = "tunnel") -> None:
        """Save export record to database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # Find challenge
            cursor.execute("SELECT id FROM challenges WHERE name = ?", (challenge_name,))
            chall_row = cursor.fetchone()
            if not chall_row:
                raise RuntimeError(f"Challenge not found in DB: {challenge_name}")

            chall_id = chall_row['id']

            # Get or create runtime instance
            cursor.execute(
                "SELECT id FROM runtime_instances WHERE challenge_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (chall_id,)
            )
            runtime_row = cursor.fetchone()

            if runtime_row:
                runtime_id = runtime_row['id']
            else:
                # Create placeholder runtime
                cursor.execute(
                    "INSERT INTO runtime_instances (challenge_id, status, container_id) VALUES (?, ?, ?)",
                    (chall_id, 'running', '')
                )
                runtime_id = cursor.lastrowid

            # Check if already exists
            cursor.execute(
                "SELECT id FROM challenge_exports WHERE runtime_id = ? AND provider = ? AND target_port = ? AND status = 'active' ORDER BY id DESC",
                (runtime_id, provider, host_port)
            )

            existing_rows = cursor.fetchall()

            if not existing_rows:
                # Insert new export record
                cursor.execute("""
                    INSERT INTO challenge_exports (runtime_id, provider, export_type, protocol, target_port, public_endpoint, pid, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (runtime_id, provider, export_type, protocol, host_port, public_endpoint, pid, 'active'))
            else:
                # Update existing record (e.g. if we restarted the tunnel)
                keep_id = existing_rows[0]["id"]
                cursor.execute("""
                    UPDATE challenge_exports
                    SET export_type = ?, public_endpoint = ?, pid = ?, status = 'active'
                    WHERE id = ?
                """, (export_type, public_endpoint, pid, keep_id))

                stale_ids = [row["id"] for row in existing_rows[1:]]
                if stale_ids:
                    placeholders = ",".join("?" for _ in stale_ids)
                    cursor.execute(
                        f"UPDATE challenge_exports SET status = 'inactive' WHERE id IN ({placeholders})",
                        stale_ids,
                    )

            conn.commit()

        finally:
            close_db_connection(conn)

    def _parse_tunnel_process(self, name: str, cmdline: list[str]) -> Optional[tuple[str, int]]:
        command = " ".join(cmdline).lower()
        basenames = {Path(part).name.lower() for part in cmdline if part}
        proc_name = (name or "").lower()

        if ("lt" in basenames or "localtunnel" in command) and "--port" in cmdline:
            try:
                index = cmdline.index("--port")
                return EXPORT_PROVIDER_LOCALTUNNEL, int(cmdline[index + 1])
            except Exception:
                return None

        if "pinggy" in basenames or proc_name == "pinggy" or "pinggy.io" in command:
            match = re.search(r"-r0:localhost:(\d+)", command)
            if match:
                return EXPORT_PROVIDER_PINGGY, int(match.group(1))
            return None

        if "ngrok" in basenames or proc_name == "ngrok":
            for index, part in enumerate(cmdline):
                if part in {"http", "tcp"} and index + 1 < len(cmdline):
                    try:
                        return EXPORT_PROVIDER_NGROK, int(cmdline[index + 1])
                    except ValueError:
                        return None
            return None

        if "cloudflared" in basenames or proc_name == "cloudflared" or "cloudflared" in command:
            match = re.search(r"(?:localhost|127\.0\.0\.1):(\d+)", command)
            if match:
                return EXPORT_PROVIDER_CLOUDFLARE, int(match.group(1))
            return None

        if "bore" in basenames or proc_name == "bore" or "bore" in command:
            if "local" in cmdline:
                try:
                    index = cmdline.index("local")
                    return EXPORT_PROVIDER_BORE, int(cmdline[index + 1])
                except Exception:
                    pass
            match = re.search(r"local\s+(\d+)", command)
            if match:
                return EXPORT_PROVIDER_BORE, int(match.group(1))
            return None

        return None

    def dedupe_active_exports(self) -> int:
        """Mark duplicate active export rows inactive, keeping newest per runtime/provider/port."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, runtime_id, provider, target_port, public_endpoint
                FROM challenge_exports
                WHERE status = 'active'
                ORDER BY id DESC
            """)
            seen: set[tuple[int, str, int]] = set()
            stale_ids: list[int] = []
            for row in cursor.fetchall():
                key = (
                    int(row["runtime_id"] or 0),
                    str(row["provider"] or ""),
                    int(row["target_port"] or 0),
                )
                if key in seen:
                    stale_ids.append(int(row["id"]))
                else:
                    seen.add(key)

            if stale_ids:
                placeholders = ",".join("?" for _ in stale_ids)
                cursor.execute(
                    f"UPDATE challenge_exports SET status = 'inactive' WHERE id IN ({placeholders})",
                    stale_ids,
                )
                conn.commit()
            return len(stale_ids)
        finally:
            close_db_connection(conn)

    def _provider_enabled(self, provider_name: str) -> bool:
        attr = {
            EXPORT_PROVIDER_NGROK: "enable_ngrok",
            EXPORT_PROVIDER_LOCALTUNNEL: "enable_localtunnel",
            EXPORT_PROVIDER_PINGGY: "enable_pinggy",
            EXPORT_PROVIDER_CLOUDFLARE: "enable_cloudflare",
            EXPORT_PROVIDER_BORE: "enable_bore",
        }.get(provider_name)
        return bool(getattr(self.config, attr, True)) if attr else True

    def _configured_base_ip(self) -> str:
        base_ip = str(getattr(self.config, "base_ip", "") or "").strip().rstrip("/")
        if not base_ip:
            return ""
        if base_ip.lower() in {"none", "null", "false", "off", "-", "0"}:
            return ""
        return base_ip

    def _direct_endpoint(self, base_ip: str, host_port: int, protocol: str) -> str:
        base_ip = str(base_ip or "").strip().rstrip("/")
        if protocol == PROTOCOL_TCP:
            clean_base = base_ip.removeprefix("tcp://").removeprefix("http://").removeprefix("https://")
            return f"tcp://{clean_base}:{host_port}"
        if base_ip.startswith(("http://", "https://")):
            return f"{base_ip}:{host_port}"
        return f"http://{base_ip}:{host_port}"

    def _backfill_direct_exports(self, challenge_name: Optional[str] = None) -> None:
        """Ensure running challenges show direct base_ip exports in status/export views."""
        base_ip = self._configured_base_ip()
        if not base_ip:
            return

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            params: list[Any] = []
            name_filter = ""
            if challenge_name:
                name_filter = "AND c.name = ?"
                params.append(challenge_name)

            cursor.execute(f"""
                SELECT ri.id AS runtime_id, c.id AS challenge_id, c.name, c.service_port, c.service_type
                FROM challenges c
                JOIN runtime_instances ri ON ri.id = (
                    SELECT id
                    FROM runtime_instances
                    WHERE challenge_id = c.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                )
                WHERE ri.status = 'running'
                {name_filter}
            """, params)

            rows = cursor.fetchall()
            for row in rows:
                port_rows = self._export_ports_for_challenge(cursor, int(row["challenge_id"]))
                if not port_rows:
                    port_rows = [{
                        "host_port": row["service_port"],
                        "service_type": row["service_type"],
                    }]

                for port in port_rows:
                    host_port = int(port["host_port"])
                    service_type = str(port["service_type"])
                    cursor.execute("""
                        SELECT id
                        FROM challenge_exports
                        WHERE runtime_id = ?
                        AND provider = ?
                        AND target_port = ?
                        AND status = 'active'
                        LIMIT 1
                    """, (row["runtime_id"], EXPORT_PROVIDER_BASE_IP, host_port))
                    if cursor.fetchone():
                        continue

                    endpoint = self._direct_endpoint(base_ip, host_port, service_type)
                    cursor.execute("""
                        INSERT INTO challenge_exports
                        (runtime_id, provider, export_type, protocol, target_port, public_endpoint, pid, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["runtime_id"],
                        EXPORT_PROVIDER_BASE_IP,
                        "direct",
                        service_type,
                        host_port,
                        endpoint,
                        None,
                        "active",
                    ))

            conn.commit()
        finally:
            close_db_connection(conn)

    def _deactivate_direct_exports_if_unconfigured(self) -> None:
        if self._configured_base_ip():
            return

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE challenge_exports
                SET status = 'inactive'
                WHERE provider = ? AND status = 'active'
            """, (EXPORT_PROVIDER_BASE_IP,))
            conn.commit()
        finally:
            close_db_connection(conn)

    def _is_tunnel_process(self, name: str, cmdline: list[str]) -> bool:
        command = " ".join(cmdline).lower()
        basenames = {Path(part).name.lower() for part in cmdline if part}
        proc_name = (name or "").lower()

        if "ngrok" in basenames or proc_name == "ngrok":
            return True

        if "pinggy" in basenames or proc_name == "pinggy" or "pinggy.io" in command:
            return True

        if "lt" in basenames and "--port" in cmdline:
            return True

        if "localtunnel" in command and "--port" in cmdline:
            return True

        if "cloudflared" in basenames or proc_name == "cloudflared" or "cloudflared" in command:
            return True

        return "bore" in basenames or proc_name == "bore" or "bore" in command

    def _ngrok_enabled(self) -> bool:
        return self._provider_enabled(EXPORT_PROVIDER_NGROK)

    def ngrok_available(self) -> bool:
        """Return True when ngrok is enabled and a token/config is available."""
        return self._ngrok_enabled() and self._ngrok_token_available()

    def _ngrok_token_available(self) -> bool:
        if os.getenv("NGROK_AUTHTOKEN", "").strip():
            return True

        cfg_tokens = getattr(self.config, "ngrok_tokens", None) or []
        if any(str(token).strip() for token in cfg_tokens):
            return True

        for path in (
            Path.home() / ".config" / "ngrok" / "ngrok.yml",
            Path.home() / ".ngrok2" / "ngrok.yml",
            Path.home() / "Library" / "Application Support" / "ngrok" / "ngrok.yml",
        ):
            try:
                if path.exists() and "authtoken:" in path.read_text(errors="ignore"):
                    return True
            except Exception:
                continue

        return False

    def _export_dict(
        self,
        challenge_name: str,
        provider: str,
        export_type: str,
        protocol: str,
        host_port: int,
        endpoint: str,
        pid: Optional[int],
        status: str,
    ) -> dict:
        return {
            "challenge": challenge_name,
            "type": export_type,
            "provider": provider,
            "protocol": protocol,
            "port": host_port,
            "url": endpoint,
            "endpoint": endpoint,
            "pid": pid,
            "status": "running" if status == "active" else status,
        }

    def _failure_dict(self, provider: str, export_type: str, exc: Exception) -> dict:
        return {
            "type": export_type,
            "provider": provider,
            "status": "failed",
            "error": str(exc),
        }

    def _export_ports_for_challenge(self, cursor, challenge_id: int) -> list[dict]:
        cursor.execute("""
            SELECT host_port, service_type
            FROM challenge_ports
            WHERE challenge_id = ?
            ORDER BY is_primary DESC, id ASC
        """, (challenge_id,))
        return [dict(row) for row in cursor.fetchall()]

    def _mark_export_inactive(self, challenge_name: str, provider: str, host_port: int = 0) -> None:
        """Mark export records as inactive."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            port_filter = ""
            params: list[Any] = [provider, challenge_name]
            if host_port:
                port_filter = "AND target_port = ?"
                params.append(host_port)

            cursor.execute(f"""
                UPDATE challenge_exports
                SET status = 'inactive'
                WHERE provider = ? AND runtime_id IN (
                    SELECT ri.id FROM runtime_instances ri
                    JOIN challenges c ON c.id = ri.challenge_id
                    WHERE c.name = ?
                ) AND status = 'active'
                {port_filter}
            """, params)

            conn.commit()

        finally:
            close_db_connection(conn)

    def _mark_id_inactive(self, export_id: int) -> None:
        """Mark a specific export ID as inactive."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE challenge_exports SET status = 'inactive' WHERE id = ?", (export_id,))
            conn.commit()
        finally:
            close_db_connection(conn)
