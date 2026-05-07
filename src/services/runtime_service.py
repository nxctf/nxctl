"""Runtime management service for Docker containers."""

import logging
import subprocess
import socket
import yaml
from pathlib import Path
from typing import Optional

from src.domain.models import Challenge, RuntimeInstance
from src.infrastructure.database import get_db_connection, close_db_connection


# NOTE: this service executes docker/compose commands on the host.



logger = logging.getLogger(__name__)


class RuntimeError(Exception):
    """Runtime operation error."""
    pass


class RuntimeService:
    """Service for managing challenge runtimes."""

    def __init__(self, db_path: str, git_cache_dir: str):
        """Initialize runtime service."""
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

            from src.domain.models import Challenge
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
                       public_url, started_at, expires_at, last_activity, last_revert, created_at
                FROM runtime_instances
                WHERE challenge_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (challenge_id,))

            row = cursor.fetchone()
            if not row:
                return None

            from src.domain.models import RuntimeInstance
            return RuntimeInstance(
                id=row["id"],
                challenge_id=row["challenge_id"],
                status=row["status"],
                container_id=row["container_id"],
                tunnel_provider=row["tunnel_provider"],
                public_url=row["public_url"],
                started_at=row["started_at"],
                expires_at=row["expires_at"],
                last_activity=row["last_activity"],
                last_revert=row["last_revert"],
                created_at=row["created_at"],
            )

        finally:
            close_db_connection(conn)

    def build(self, challenge_name: str) -> str:
        """Build Docker image for a challenge."""
        # Get challenge from DB
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        # Find challenge directory in git cache (convert to absolute path)
        challenge_dir = (self.git_cache_dir / challenge.path).resolve()
        if not challenge_dir.exists():
            raise RuntimeError(f"Challenge directory not found: {challenge_dir}")

        # Check for docker-compose.yml
        docker_compose = challenge_dir / "docker-compose.yml"
        if not docker_compose.exists():
            raise RuntimeError(f"docker-compose.yml not found in {challenge_dir}")

        # Build using docker compose (v2 with fallback to v1)
        logger.info(f"Building image for challenge: {challenge_name}")

        try:
            # Try docker compose v2 first
            cmd = ["docker", "compose", "-f", str(docker_compose), "build"]
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=True,
                )
                logger.info(f"Successfully built image for {challenge_name}")
                return f"{challenge_name}:latest"

            except FileNotFoundError:
                # Fallback to docker-compose v1
                logger.info("docker compose v2 not found, trying docker-compose v1...")
                cmd = ["docker-compose", "-f", str(docker_compose), "build"]
                result = subprocess.run(
                    cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=True,
                )
                logger.info(f"Successfully built image for {challenge_name}")
                return f"{challenge_name}:latest"

        except subprocess.TimeoutExpired:
            raise RuntimeError("Build operation timed out")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Build failed: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Build failed: {str(e)}")

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use on the host."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def _find_free_port(self, start_port: int) -> int:
        """Find the next available port starting from start_port."""
        port = start_port
        while self._is_port_in_use(port):
            port += 1
        return port

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

    def start(self, challenge_name: str) -> RuntimeInstance:
        """Start a challenge runtime."""
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
            return runtime

        # Find challenge directory (convert to absolute path)
        challenge_dir = (self.git_cache_dir / challenge.path).resolve()
        if not challenge_dir.exists():
            raise RuntimeError(f"Challenge directory not found: {challenge_dir}")

        docker_compose = challenge_dir / "docker-compose.yml"
        if not docker_compose.exists():
            raise RuntimeError(f"docker-compose.yml not found in {challenge_dir}")

        # Load and modify docker-compose.yml to override ports
        try:
            with open(docker_compose, 'r') as f:
                compose_data = yaml.safe_load(f) or {}

            # Determine the port to use
            # Use the port from DB, but if it's busy or 0, find a free one
            original_port = challenge.service_port
            if original_port == 0 or self._is_port_in_use(original_port):
                # Start searching from 9000 if 0, or from the next port if busy
                start_search = 9000 if original_port == 0 else original_port + 1
                new_port = self._find_free_port(start_search)
                logger.info(f"Port {original_port} is busy or 0, using {new_port} instead")

                # Update DB and object
                self._update_challenge_port(challenge.id, new_port)
                challenge.service_port = new_port

            desired_port = challenge.service_port

            # Override ports in compose_data
            if 'services' in compose_data:
                # We prioritize the first service found or the one named 'challenge' or similar
                # For now, we'll apply it to the first service that seems to be the main one
                for service_name, service_config in compose_data['services'].items():
                    # If the service has ports, override the host part of the FIRST port
                    if 'ports' in service_config and service_config['ports']:
                        new_ports = []
                        for i, p in enumerate(service_config['ports']):
                            if i == 0:  # Only override the primary port to avoid host-side collisions
                                if isinstance(p, str):
                                    if ':' in p:
                                        _, container_p = p.split(':')
                                        new_ports.append(f"{desired_port}:{container_p}")
                                    else:
                                        new_ports.append(f"{desired_port}:{p}")
                                elif isinstance(p, dict):
                                    p_copy = p.copy()
                                    p_copy['published'] = desired_port
                                    new_ports.append(p_copy)
                                else:
                                    new_ports.append(f"{desired_port}:{p}")
                            else:
                                # Keep other ports as is
                                new_ports.append(p)
                        service_config['ports'] = new_ports
                    elif not any('ports' in s for s in compose_data['services'].values()):
                        # If NO service has ports defined, inject it into the first service
                        # This handles the case where port is missing in docker-compose
                        service_config['ports'] = [f"{desired_port}:{desired_port}"]
                        break # Only inject into one service

            # Write temporary compose file to avoid modifying the original
            docker_compose_run = challenge_dir / "docker-compose.run.yml"
            with open(docker_compose_run, 'w') as f:
                yaml.dump(compose_data, f)

            # Start with docker compose (v2 with fallback to v1) using the new file
            logger.info(f"Starting challenge: {challenge_name} on port {desired_port}")

            # Try docker compose v2 first
            cmd = ["docker", "compose", "-f", str(docker_compose_run), "up", "-d"]
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
            except FileNotFoundError:
                # Fallback to docker-compose v1
                logger.info("docker compose v2 not found, trying docker-compose v1...")
                cmd = ["docker-compose", "-f", str(docker_compose_run), "up", "-d"]
                result = subprocess.run(
                    cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )

            # Get container ID from docker compose
            ps_cmd = ["docker", "compose", "-f", str(docker_compose_run), "ps", "-q"]
            try:
                container_result = subprocess.run(
                    ps_cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
            except FileNotFoundError:
                # Fallback to docker-compose v1
                ps_cmd = ["docker-compose", "-f", str(docker_compose_run), "ps", "-q"]
                container_result = subprocess.run(
                    ps_cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )

            container_id = container_result.stdout.strip().split("\n")[0] if container_result.stdout.strip() else "unknown"

            # Save to database
            challenge_id = challenge.id
            if challenge_id is None:
                raise RuntimeError(f"Invalid challenge id for {challenge_name}")

            self._save_runtime_to_db(
                challenge_id=challenge_id,
                status="running",
                container_id=container_id,
            )


            logger.info(f"Successfully started challenge: {challenge_name}")

            # Fetch and return the created runtime
            runtime = self._get_runtime_from_db(challenge_id)
            if not runtime:


                raise RuntimeError("Failed to retrieve runtime instance")

            return runtime

        except subprocess.TimeoutExpired:
            raise RuntimeError("Start operation timed out")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Start failed: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Start failed: {str(e)}")

    def stop(self, challenge_name: str) -> bool:
        """Stop a challenge runtime."""
        # Get challenge from DB
        challenge = self._get_challenge_from_db(challenge_name)
        if not challenge:
            raise RuntimeError(f"Challenge not found: {challenge_name}")

        # Find challenge directory (convert to absolute path)
        challenge_dir = (self.git_cache_dir / challenge.path).resolve()
        if not challenge_dir.exists():
            raise RuntimeError(f"Challenge directory not found: {challenge_dir}")

        docker_compose = challenge_dir / "docker-compose.yml"
        docker_compose_run = challenge_dir / "docker-compose.run.yml"

        # Use the temporary run file if it exists, otherwise use original
        target_compose = docker_compose_run if docker_compose_run.exists() else docker_compose

        if not target_compose.exists():
            raise RuntimeError(f"No docker-compose file found in {challenge_dir}")

        # Stop with docker compose (v2 with fallback to v1)
        logger.info(f"Stopping challenge: {challenge_name}")

        try:
            # Prefer docker compose v2
            cmd = ["docker", "compose", "-f", str(target_compose), "down", "--remove-orphans", "-v"]
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
            except FileNotFoundError:
                logger.info("docker compose v2 not found, trying docker-compose v1...")
                cmd = ["docker-compose", "-f", str(docker_compose), "down", "--remove-orphans", "-v"]
                result = subprocess.run(
                    cmd,
                    cwd=str(challenge_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )

            if result.returncode != 0:
                raise RuntimeError(f"Stop failed: {result.stderr}")

            # Update database status
            self._update_runtime_status(challenge.id, "stopped")

            logger.info(f"Successfully stopped challenge: {challenge_name}")
            return True

        except subprocess.TimeoutExpired:
            raise RuntimeError("Stop operation timed out")
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
            from src.domain.models import RuntimeInstance
            return RuntimeInstance(
                challenge_id=challenge.id,
                status="stopped",
                container_id=None,
            )

        return runtime

    def _save_runtime_to_db(self, challenge_id: int, status: str, container_id: str = "") -> None:
        """Save runtime instance to database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO runtime_instances
                (challenge_id, status, container_id)
                VALUES (?, ?, ?)
            """, (challenge_id, status, container_id))

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
                WHERE challenge_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (status, challenge_id))

            conn.commit()
            logger.debug(f"Runtime status updated: challenge_id={challenge_id}, status={status}")

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to update runtime status: {str(e)}")
        finally:
            close_db_connection(conn)
