"""Export/tunnel management orchestrator."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from nxctl.core.db import get_db_connection, close_db_connection
from nxctl.core.constants import (
    EXPORT_PROVIDER_NGROK,
    EXPORT_PROVIDER_LOCALTUNNEL,
    EXPORT_PROVIDER_PINGGY,
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

            self.providers: Dict[str, Any] = {
                EXPORT_PROVIDER_NGROK: NgrokProvider(config),
                EXPORT_PROVIDER_LOCALTUNNEL: LocaltunnelProvider(config),
                EXPORT_PROVIDER_PINGGY: PinggyProvider(config),
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
        base_ip = str(getattr(self.config, "base_ip", "") or "").strip().rstrip("/")
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

        if str(getattr(self.config, "base_ip", "") or "").strip():
            attempted.add(EXPORT_PROVIDER_BASE_IP)
            try:
                exports.append(self.start_direct_export(challenge_name, host_port, protocol))
            except Exception as exc:
                failures.append(self._failure_dict(EXPORT_PROVIDER_BASE_IP, "direct", exc))

        if protocol != PROTOCOL_TCP and self._ngrok_enabled() and self._ngrok_token_available():
            attempted.add(EXPORT_PROVIDER_NGROK)
            try:
                exports.append(
                    self.start_export_details(
                        challenge_name,
                        host_port,
                        protocol,
                        EXPORT_PROVIDER_NGROK,
                    )
                )
            except Exception as exc:
                failures.append(self._failure_dict(EXPORT_PROVIDER_NGROK, "tunnel", exc))

        for provider_name in default_providers or self.default_providers_for(protocol):
            if not provider_name or provider_name in attempted:
                continue
            attempted.add(provider_name)
            if not self._provider_enabled(provider_name):
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
                break
            except Exception as exc:
                failures.append(self._failure_dict(provider_name, "tunnel", exc))

        if not exports and failures:
            raise RuntimeError("; ".join(f"{f['provider']}: {f['error']}" for f in failures))

        return exports, failures

    def default_providers_for(self, protocol: str) -> list[str]:
        """Return the existing protocol-based default tunnel providers."""
        if protocol == PROTOCOL_TCP:
            return [EXPORT_PROVIDER_PINGGY]
        return [EXPORT_PROVIDER_LOCALTUNNEL]

    def stop_export(self, challenge_name: str, provider_name: str, host_port: int = 0) -> bool:
        """Stop an export."""
        if provider_name == EXPORT_PROVIDER_BASE_IP:
            self._mark_export_inactive(challenge_name, provider_name)
            return True

        provider = self.get_provider(provider_name)
        if not provider:
            raise RuntimeError(f"Unknown provider: {provider_name}")

        # Stop the export
        stopped = provider.stop(challenge_name, host_port)

        # Mark as inactive in database
        self._mark_export_inactive(challenge_name, provider_name)

        return stopped

    def stop_all_exports(self, challenge_name: str) -> list[dict]:
        """Stop every active export for a challenge."""
        stopped_exports = []
        for export in self.list_exports(challenge_name, check_health=False):
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
        """Kill orphaned ngrok, localtunnel, and pinggy processes."""
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

        try:
            return bool(provider.is_running(export.get("challenge") or "", int(export.get("port") or 0)))
        except Exception:
            pass

        pid = export.get('pid')
        if not pid:
            return True  # Assume alive if no PID stored (for legacy)

        return provider.is_pid_running(pid)

    def list_exports(self, challenge_name: Optional[str] = None, check_health: bool = True) -> list:
        """List all active exports."""
        self._backfill_direct_exports(challenge_name)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            if challenge_name:
                cursor.execute("""
                    SELECT ce.id, c.name, ri.status AS runtime_status, ce.provider, ce.export_type, ce.protocol, ce.target_port, ce.public_endpoint, ce.pid, ce.status, ce.created_at
                    FROM challenge_exports ce
                    JOIN runtime_instances ri ON ce.runtime_id = ri.id
                    JOIN challenges c ON c.id = ri.challenge_id
                    WHERE c.name = ? AND ce.status = 'active'
                    ORDER BY CASE WHEN ce.provider = 'base_ip' THEN 0 ELSE 1 END, ce.created_at ASC
                """, (challenge_name,))
            else:
                cursor.execute("""
                    SELECT ce.id, c.name, ri.status AS runtime_status, ce.provider, ce.export_type, ce.protocol, ce.target_port, ce.public_endpoint, ce.pid, ce.status, ce.created_at
                    FROM challenge_exports ce
                    JOIN runtime_instances ri ON ce.runtime_id = ri.id
                    JOIN challenges c ON c.id = ri.challenge_id
                    WHERE ce.status = 'active'
                    ORDER BY c.name ASC, CASE WHEN ce.provider = 'base_ip' THEN 0 ELSE 1 END, ce.created_at ASC
                """)

            exports = []
            for row in cursor.fetchall():
                export_data = {
                    'id': row['id'],
                    'challenge': row['name'],
                    'id': row['id'],
                    'runtime_status': row['runtime_status'],
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
        """Check all active exports and mark those with dead PIDs as inactive."""
        exports = self.list_exports(check_health=True)
        dead_count = 0

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            for export in exports:
                if export['status'] == 'dead':
                    cursor.execute("UPDATE challenge_exports SET status = 'inactive' WHERE id = ?", (export['id'],))
                    dead_count += 1

            conn.commit()
            return dead_count
        finally:
            close_db_connection(conn)

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
                "SELECT id FROM challenge_exports WHERE runtime_id = ? AND provider = ? AND target_port = ? AND status = 'active'",
                (runtime_id, provider, host_port)
            )

            if not cursor.fetchone():
                # Insert new export record
                cursor.execute("""
                    INSERT INTO challenge_exports (runtime_id, provider, export_type, protocol, target_port, public_endpoint, pid, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (runtime_id, provider, export_type, protocol, host_port, public_endpoint, pid, 'active'))
            else:
                # Update existing record (e.g. if we restarted the tunnel)
                cursor.execute("""
                    UPDATE challenge_exports
                    SET export_type = ?, public_endpoint = ?, pid = ?, status = 'active'
                    WHERE runtime_id = ? AND provider = ? AND target_port = ?
                """, (export_type, public_endpoint, pid, runtime_id, provider, host_port))

            conn.commit()

        finally:
            close_db_connection(conn)

    def _provider_enabled(self, provider_name: str) -> bool:
        attr = {
            EXPORT_PROVIDER_NGROK: "enable_ngrok",
            EXPORT_PROVIDER_LOCALTUNNEL: "enable_localtunnel",
            EXPORT_PROVIDER_PINGGY: "enable_pinggy",
        }.get(provider_name)
        return bool(getattr(self.config, attr, True)) if attr else True

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
        base_ip = str(getattr(self.config, "base_ip", "") or "").strip().rstrip("/")
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
                SELECT ri.id AS runtime_id, c.name, c.service_port, c.service_type
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
                cursor.execute("""
                    SELECT id
                    FROM challenge_exports
                    WHERE runtime_id = ?
                    AND provider = ?
                    AND status = 'active'
                    LIMIT 1
                """, (row["runtime_id"], EXPORT_PROVIDER_BASE_IP))
                if cursor.fetchone():
                    continue

                endpoint = self._direct_endpoint(base_ip, int(row["service_port"]), row["service_type"])
                cursor.execute("""
                    INSERT INTO challenge_exports
                    (runtime_id, provider, export_type, protocol, target_port, public_endpoint, pid, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["runtime_id"],
                    EXPORT_PROVIDER_BASE_IP,
                    "direct",
                    row["service_type"],
                    int(row["service_port"]),
                    endpoint,
                    None,
                    "active",
                ))

            conn.commit()
        finally:
            close_db_connection(conn)

    def _is_tunnel_process(self, name: str, cmdline: list[str]) -> bool:
        command = " ".join(cmdline).lower()
        basenames = {Path(part).name.lower() for part in cmdline if part}
        proc_name = (name or "").lower()

        if "ngrok" in basenames or proc_name == "ngrok":
            return True

        if "pinggy" in basenames or proc_name == "pinggy" or "tcp@free.pinggy.io" in command:
            return True

        if "lt" in basenames and "--port" in cmdline:
            return True

        return "localtunnel" in command and "--port" in cmdline

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

    def _mark_export_inactive(self, challenge_name: str, provider: str) -> None:
        """Mark export records as inactive."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE challenge_exports
                SET status = 'inactive'
                WHERE provider = ? AND runtime_id IN (
                    SELECT ri.id FROM runtime_instances ri
                    JOIN challenges c ON c.id = ri.challenge_id
                    WHERE c.name = ?
                ) AND status = 'active'
            """, (provider, challenge_name))

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
