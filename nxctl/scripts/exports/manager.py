"""Export/tunnel management orchestrator."""

import logging
from typing import Dict, Optional

from src.scripts.exports.base import ExportProvider
from src.scripts.exports.ngrok import NgrokProvider
from src.scripts.exports.localtunnel import LocaltunnelProvider
from src.scripts.exports.pinggy import PinggyProvider
from src.core.db import get_db_connection, close_db_connection
from src.core.constants import (
    EXPORT_PROVIDER_NGROK,
    EXPORT_PROVIDER_LOCALTUNNEL,
    EXPORT_PROVIDER_PINGGY,
    EXPORT_PROVIDERS,
)

logger = logging.getLogger(__name__)


class ExportManager:
    """Manages tunnel exports for challenges."""

    def __init__(self, config, db_path: str):
        """Initialize export manager."""
        self.config = config
        self.db_path = db_path
        self.providers: Dict[str, ExportProvider] = {
            EXPORT_PROVIDER_NGROK: NgrokProvider(config),
            EXPORT_PROVIDER_LOCALTUNNEL: LocaltunnelProvider(config),
            EXPORT_PROVIDER_PINGGY: PinggyProvider(config),
        }

    def get_provider(self, provider_name: str) -> Optional[ExportProvider]:
        """Get a provider by name."""
        return self.providers.get(provider_name)

    def start_export(self, challenge_name: str, host_port: int, protocol: str, provider_name: str) -> str:
        """Start an export with a specific provider.

        Returns:
            Public URL/endpoint
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise RuntimeError(f"Unknown provider: {provider_name}")

        if not provider.supports_protocol(protocol):
            raise RuntimeError(f"Provider {provider_name} does not support {protocol} protocol")

        # Start the export
        result = provider.start(challenge_name, host_port, protocol)

        # Save to database
        self._save_export_to_db(challenge_name, provider_name, protocol, host_port, result.url, result.pid)

        return result.url

    def stop_export(self, challenge_name: str, provider_name: str, host_port: int = 0) -> bool:
        """Stop an export."""
        provider = self.get_provider(provider_name)
        if not provider:
            raise RuntimeError(f"Unknown provider: {provider_name}")

        # Stop the export
        stopped = provider.stop(challenge_name, host_port)

        # Mark as inactive in database
        self._mark_export_inactive(challenge_name, provider_name)

        return stopped

    def check_export_alive(self, export: dict) -> bool:
        """Check if an export is actually alive by PID."""
        provider = self.get_provider(export['provider'])
        if not provider:
            return False

        pid = export.get('pid')
        if not pid:
            return True # Assume alive if no PID stored (for legacy)

        return provider.is_pid_running(pid)

    def list_exports(self, challenge_name: Optional[str] = None, check_health: bool = True) -> list:
        """List all active exports."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            if challenge_name:
                cursor.execute("""
                    SELECT ce.id, c.name, ce.provider, ce.protocol, ce.target_port, ce.public_endpoint, ce.pid, ce.status, ce.created_at
                    FROM challenge_exports ce
                    JOIN runtime_instances ri ON ce.runtime_id = ri.id
                    JOIN challenges c ON c.id = ri.challenge_id
                    WHERE c.name = ? AND ce.status = 'active'
                    ORDER BY ce.created_at DESC
                """, (challenge_name,))
            else:
                cursor.execute("""
                    SELECT ce.id, c.name, ce.provider, ce.protocol, ce.target_port, ce.public_endpoint, ce.pid, ce.status, ce.created_at
                    FROM challenge_exports ce
                    JOIN runtime_instances ri ON ce.runtime_id = ri.id
                    JOIN challenges c ON c.id = ri.challenge_id
                    WHERE ce.status = 'active'
                    ORDER BY ce.created_at DESC
                """)

            exports = []
            for row in cursor.fetchall():
                export_data = {
                    'id': row['id'],
                    'challenge': row['name'],
                    'provider': row['provider'],
                    'protocol': row['protocol'],
                    'port': row['target_port'],
                    'endpoint': row['public_endpoint'],
                    'pid': row['pid'],
                    'status': row['status'],
                    'created_at': row['created_at'],
                }

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

    def _save_export_to_db(self, challenge_name: str, provider: str, protocol: str, host_port: int, public_endpoint: str, pid: Optional[int] = None) -> None:
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
                "SELECT id FROM runtime_instances WHERE challenge_id = ? ORDER BY created_at DESC LIMIT 1",
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
                    INSERT INTO challenge_exports (runtime_id, provider, protocol, target_port, public_endpoint, pid, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (runtime_id, provider, protocol, host_port, public_endpoint, pid, 'active'))
            else:
                # Update existing record (e.g. if we restarted the tunnel)
                cursor.execute("""
                    UPDATE challenge_exports
                    SET public_endpoint = ?, pid = ?, status = 'active'
                    WHERE runtime_id = ? AND provider = ? AND target_port = ?
                """, (public_endpoint, pid, runtime_id, provider, host_port))

            conn.commit()

        finally:
            close_db_connection(conn)

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
