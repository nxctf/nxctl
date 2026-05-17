"""Runtime management service for Docker containers."""

import logging
from pathlib import Path
from typing import Optional
import yaml
from datetime import datetime, timedelta

from nxctl.core.models import Challenge, RuntimeInstance
from nxctl.core.db import get_db_connection, close_db_connection
from nxctl.core.docker import run_docker_compose_build, run_docker_compose_up, run_docker_compose_down_with_cleanup, DockerError
from nxctl.core.utils import is_port_in_use, find_free_port

logger = logging.getLogger(__name__)


class RuntimeError(Exception):
    """Runtime operation error."""
    pass


class RuntimeService:
    """Service for managing challenge runtimes."""

    def __init__(self, config, db_path: str, git_cache_dir: str):
        """Initialize runtime service."""
        self.config = config
        self.db_path = db_path
        self.git_cache_dir = Path(git_cache_dir)

    def _get_challenge_from_db(self, name: str) -> Optional[Challenge]:
        """Get challenge from database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, name, path, service_port, service_type, enabled, created_at
                FROM challenges
                WHERE name = ?
            """, (name,))

            row = cursor.fetchone()
            if not row:
                return None

            return Challenge(
                id=row["id"],
                name=row["name"],
                path=row["path"],
                service_port=row["service_port"],
                service_type=row["service_type"],
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
            )

        finally:
            close_db_connection(conn)

    def _get_runtime_from_db(self, challenge_id: int) -> Optional[RuntimeInstance]:
        """Get runtime instance from database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, challenge_id, status, container_id, tunnel_provider,
                       public_url, started_at, expires_at, last_activity, last_revert, last_restart, created_at
                FROM runtime_instances
                WHERE challenge_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (challenge_id,))

            row = cursor.fetchone()
            if not row:
                return None

            def parse_date(val):
                if not val: return None
                if isinstance(val, datetime): return val
                try:
                    return datetime.strptime(val, '%Y-%m-%d %H:%M:%S')
                except:
                    return val

            return RuntimeInstance(
                id=row["id"],
                challenge_id=row["challenge_id"],
                status=row["status"],
                container_id=row["container_id"],
                tunnel_provider=row["tunnel_provider"],
                public_url=row["public_url"],
                started_at=parse_date(row["started_at"]),
                expires_at=parse_date(row["expires_at"]),
                last_activity=parse_date(row["last_activity"]),
                last_revert=parse_date(row["last_revert"]),
                last_restart=parse_date(row["last_restart"]),
                created_at=parse_date(row["created_at"]),
            )

        finally:
            close_db_connection(conn)

    def extend_time(self, challenge_name: str) -> RuntimeInstance:
        """Extend runtime by N minutes."""
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        runtime = self._get_runtime_from_db(challenge.id)
        if not runtime or runtime.status != "running":
            raise RuntimeError(f"Challenge not running: {challenge_name}")

        cooldown_remaining = self.check_extend_cooldown(challenge_name)
        if cooldown_remaining:
            raise RuntimeError(
                f"Extend cooldown active. Wait {cooldown_remaining}s"
            )

        if not runtime.expires_at:
            raise RuntimeError("Challenge has no expiration time")

        # Calculate remaining time
        expires_at = runtime.expires_at
        remaining = expires_at - datetime.now()
        remaining_mins = remaining.total_seconds() / 60

        if remaining_mins > self.config.extend_threshold_minutes:
            raise RuntimeError(f"Can only extend when remaining time is less than {self.config.extend_threshold_minutes} minutes")

        new_expires_at = expires_at + timedelta(minutes=self.config.extend_time_minutes)

        self._update_runtime_expiry(challenge.id, new_expires_at)
        self.update_extend_time(challenge_name)
        logger.info(f"Extended {challenge_name} expiry to {new_expires_at}")

        return self._get_runtime_from_db(challenge.id)

    def check_restart_cooldown(self, challenge_name: str) -> Optional[int]:
        """Check if challenge can be restarted. Returns remaining seconds or None."""
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            return None

        runtime = self._get_runtime_from_db(challenge.id)
        if not runtime or not runtime.last_restart:
            return None

        elapsed = (datetime.now() - runtime.last_restart).total_seconds()
        if elapsed < self.config.restart_cooldown_seconds:
            return int(self.config.restart_cooldown_seconds - elapsed)
        return None

    def check_extend_cooldown(self, challenge_name: str) -> Optional[int]:
        """Check extend cooldown. Returns remaining seconds or None."""
        cooldown_seconds = int(getattr(self.config, "extend_cooldown_seconds", 30) or 0)
        if cooldown_seconds <= 0:
            return None

        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            return None

        runtime = self._get_runtime_from_db(challenge.id)
        if not runtime or not runtime.last_activity:
            return None

        elapsed = (datetime.now() - runtime.last_activity).total_seconds()
        if elapsed < cooldown_seconds:
            return int(cooldown_seconds - elapsed)
        return None

    def update_restart_time(self, challenge_name: str):
        """Update last_restart timestamp."""
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            return

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE runtime_instances SET last_restart = datetime('now', 'localtime') WHERE challenge_id = ?",
                (challenge.id,)
            )
            conn.commit()
        finally:
            close_db_connection(conn)

    def update_extend_time(self, challenge_name: str):
        """Update last_activity timestamp after a successful extend."""
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            return

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE runtime_instances SET last_activity = datetime('now', 'localtime') WHERE challenge_id = ?",
                (challenge.id,)
            )
            conn.commit()
        finally:
            close_db_connection(conn)

    def stop_expired_runtimes(self) -> list[str]:
        """Check for and stop all expired runtimes."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        stopped = []

        try:
            cursor.execute("""
                SELECT c.name
                FROM runtime_instances r
                JOIN challenges c ON r.challenge_id = c.id
                WHERE r.status = 'running'
                AND r.expires_at IS NOT NULL
                AND r.expires_at < datetime('now', 'localtime')
            """)

            expired = [row["name"] for row in cursor.fetchall()]
            for name in expired:
                try:
                    self.stop(name)
                    stopped.append(name)
                except Exception as e:
                    logger.error(f"Failed to stop expired challenge {name}: {e}")

            return stopped
        finally:
            close_db_connection(conn)

    def _update_runtime_expiry(self, challenge_id: int, expires_at: datetime) -> None:
        """Update runtime expiration in database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE runtime_instances
                SET expires_at = ?
                WHERE challenge_id = ?
                AND status = 'running'
            """, (expires_at.strftime('%Y-%m-%d %H:%M:%S'), challenge_id))
            conn.commit()
        finally:
            close_db_connection(conn)

    def build(self, challenge_name: str) -> str:
        """Build Docker image for a challenge."""
        # Get challenge from DB
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        # Find challenge directory
        challenge_dir = (self.git_cache_dir / challenge.path).resolve()
        if not challenge_dir.exists():
            raise RuntimeError(f"Challenge directory not found: {challenge_dir}")

        # Find docker-compose.yml
        docker_compose = challenge_dir / "docker-compose.yml"
        if not docker_compose.exists():
            raise RuntimeError(f"docker-compose.yml not found in {challenge_dir}")

        try:
            logger.info(f"Building image for challenge: {challenge_name}")
            run_docker_compose_build(docker_compose, cwd=challenge_dir)
            logger.info(f"Successfully built image for {challenge_name}")
            return f"{challenge_name}:latest"
        except DockerError as e:
            raise RuntimeError(f"Build failed: {str(e)}")

    def start(self, challenge_name: str) -> RuntimeInstance:
        """Start a challenge runtime (includes automatic build)."""
        # Get challenge from DB
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        if not challenge.enabled:
            raise RuntimeError(f"Challenge is disabled: {challenge_name}")

        # Check if already running
        runtime = self._get_runtime_from_db(challenge.id)
        if runtime and runtime.status == "running":
            logger.info(f"Challenge already running: {challenge_name}")
            # Backfill expiry if missing
            if not runtime.expires_at:
                expires_at = datetime.now() + timedelta(minutes=self.config.default_ttl_minutes)
                self._update_runtime_expiry(challenge.id, expires_at)
                runtime.expires_at = expires_at
            return runtime

        # Find challenge directory
        challenge_dir = (self.git_cache_dir / challenge.path).resolve()
        if not challenge_dir.exists():
            raise RuntimeError(f"Challenge directory not found: {challenge_dir}")

        docker_compose = challenge_dir / "docker-compose.yml"
        if not docker_compose.exists():
            raise RuntimeError(f"docker-compose.yml not found in {challenge_dir}")

        # Auto-build before starting
        try:
            logger.info(f"Building image for challenge: {challenge_name}")
            run_docker_compose_build(docker_compose, cwd=challenge_dir)
            logger.info(f"Successfully built image for {challenge_name}")
        except DockerError as e:
            raise RuntimeError(f"Build failed: {str(e)}")

        try:
            # Determine port to use
            desired_port = challenge.service_port
            if is_port_in_use(desired_port):
                logger.info(f"Port {desired_port} is in use, finding free port...")
                desired_port = find_free_port(desired_port + 1)
                self._update_challenge_port(challenge.id, desired_port)
                challenge.service_port = desired_port

            # Load and modify docker-compose
            with open(docker_compose, 'r') as f:
                compose_data = yaml.safe_load(f) or {}

            # Update ports in compose
            if 'services' in compose_data:
                for service_name, service_config in compose_data['services'].items():
                    if isinstance(service_config, dict) and 'ports' in service_config:
                        new_ports = []
                        for i, port_spec in enumerate(service_config['ports']):
                            if i == 0:  # Override only the primary port
                                if isinstance(port_spec, str) and ':' in port_spec:
                                    _, container_port = port_spec.split(':')
                                    new_ports.append(f"{desired_port}:{container_port}")
                                else:
                                    new_ports.append(f"{desired_port}:{port_spec}")
                            else:
                                new_ports.append(port_spec)
                        service_config['ports'] = new_ports

            # Write modified compose to temporary file
            docker_compose_run = challenge_dir / "docker-compose.run.yml"
            with open(docker_compose_run, 'w') as f:
                yaml.safe_dump(compose_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Starting challenge: {challenge_name} on port {desired_port}")
            run_docker_compose_up(docker_compose_run, cwd=challenge_dir, detach=True)

            # Set expiry
            expires_at = datetime.now() + timedelta(minutes=self.config.default_ttl_minutes)

            # Save to database
            if challenge.id is None:
                raise RuntimeError(f"Invalid challenge id for {challenge_name}")

            self._save_runtime_to_db(
                challenge_id=challenge.id,
                status="running",
                container_id="",
                expires_at=expires_at
            )

            logger.info(f"Successfully started challenge: {challenge_name}")

            # Fetch and return the created runtime
            runtime = self._get_runtime_from_db(challenge.id)
            if not runtime:
                raise RuntimeError("Failed to retrieve runtime instance")

            return runtime

        except DockerError as e:
            raise RuntimeError(f"Start failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Start failed: {str(e)}")

    def stop(
        self,
        challenge_name: str,
        remove_volumes: bool = False,
        remove_images: Optional[str] = None,
        remove_orphans: bool = True,
    ) -> bool:
        """Stop a challenge runtime."""
        # Get challenge from DB
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        # Find challenge directory
        challenge_dir = (self.git_cache_dir / challenge.path).resolve()
        if not challenge_dir.exists():
            raise RuntimeError(f"Challenge directory not found: {challenge_dir}")

        docker_compose = challenge_dir / "docker-compose.yml"
        docker_compose_run = challenge_dir / "docker-compose.run.yml"

        # Use the temporary run file if it exists, otherwise use original
        target_compose = docker_compose_run if docker_compose_run.exists() else docker_compose

        if not target_compose.exists():
            raise RuntimeError(f"No docker-compose file found in {challenge_dir}")

        try:
            logger.info(f"Stopping challenge: {challenge_name}")
            run_docker_compose_down_with_cleanup(
                target_compose,
                cwd=challenge_dir,
                remove_volumes=remove_volumes,
                remove_images=remove_images,
                remove_orphans=remove_orphans,
            )

            # Update database status
            if challenge.id:
                self._update_runtime_status(challenge.id, "stopped")

            logger.info(f"Successfully stopped challenge: {challenge_name}")
            return True

        except DockerError as e:
            raise RuntimeError(f"Stop failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Stop failed: {str(e)}")

    def status(self, challenge_name: str) -> RuntimeInstance:
        """Get status of a challenge runtime."""
        # Get challenge from DB
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        # Get runtime
        runtime = self._get_runtime_from_db(challenge.id)
        if not runtime:
            # No runtime created yet
            return RuntimeInstance(
                challenge_id=challenge.id,
                status="stopped",
                container_id=None,
            )

        # Auto-backfill expiry for legacy records that are still running
        if runtime.status == 'running' and not runtime.expires_at:
            expires_at = datetime.now() + timedelta(minutes=self.config.default_ttl_minutes)
            self._update_runtime_expiry(challenge.id, expires_at)
            runtime.expires_at = expires_at

        return runtime

    def _save_runtime_to_db(self, challenge_id: int, status: str, container_id: str = "", expires_at: datetime = None) -> None:
        """Save runtime instance to database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO runtime_instances
                (challenge_id, status, container_id, started_at, expires_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'), ?)
            """, (challenge_id, status, container_id, expires_at.strftime('%Y-%m-%d %H:%M:%S') if expires_at else None))

            conn.commit()
            logger.debug(f"Runtime instance saved for challenge_id={challenge_id}")

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to save runtime: {str(e)}")
        finally:
            close_db_connection(conn)

    def _update_runtime_status(self, challenge_id: int, status: str) -> None:
        """Update runtime status in database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE runtime_instances
                SET status = ?
                WHERE id = (
                    SELECT id FROM runtime_instances
                    WHERE challenge_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                )
            """, (status, challenge_id))

            conn.commit()
            logger.debug(f"Runtime status updated: challenge_id={challenge_id}, status={status}")

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to update runtime status: {str(e)}")
        finally:
            close_db_connection(conn)

    def _update_challenge_port(self, challenge_id: int, port: int) -> None:
        """Update challenge service port in database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE challenges SET service_port = ? WHERE id = ?", (port, challenge_id))
            conn.commit()
            logger.info(f"Updated challenge {challenge_id} port to {port} in database")
        finally:
            close_db_connection(conn)
