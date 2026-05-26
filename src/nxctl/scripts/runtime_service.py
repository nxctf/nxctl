"""Runtime management service for Docker containers."""

import copy
import logging
import random
import socket
from pathlib import Path
from typing import Optional
import yaml
from datetime import datetime, timedelta

from nxctl.core.models import Challenge, RuntimeInstance
from nxctl.core.db import get_db_connection, close_db_connection
from nxctl.core.docker import run_docker_compose_build, run_docker_compose_up, run_docker_compose_down_with_cleanup, DockerError
from nxctl.core.utils import is_port_in_use, safe_runtime_name
from nxctl.core.yaml import extract_ports_from_compose

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
        self.git_cache_dir = Path(git_cache_dir).resolve()
        self.compose_dir = config.compose_dir

    def _runtime_compose_file(self, challenge_name: str) -> Path:
        return (self.compose_dir / f"{safe_runtime_name(challenge_name)}.docker-compose.yml").resolve()

    def _legacy_runtime_compose_file(self, challenge_dir: Path) -> Path:
        return challenge_dir / "docker-compose.run.yml"

    def _absolute_compose_path(self, challenge_dir: Path, value):
        if not isinstance(value, str) or not value.strip():
            return value
        raw = value.strip()
        if "://" in raw or raw.startswith("${"):
            return value
        path = Path(raw).expanduser()
        if path.is_absolute():
            return str(path)
        return str((challenge_dir / path).resolve())

    def _prepare_external_runtime_compose(self, compose_data: dict, challenge_dir: Path) -> dict:
        """Make relative host paths valid when the generated compose lives outside the challenge dir."""
        services = compose_data.get("services")
        if not isinstance(services, dict):
            return compose_data

        for service_config in services.values():
            if not isinstance(service_config, dict):
                continue

            build = service_config.get("build")
            if isinstance(build, str):
                service_config["build"] = self._absolute_compose_path(challenge_dir, build)
            elif isinstance(build, dict) and build.get("context"):
                build["context"] = self._absolute_compose_path(challenge_dir, build["context"])

            env_file = service_config.get("env_file")
            if isinstance(env_file, str):
                service_config["env_file"] = self._absolute_compose_path(challenge_dir, env_file)
            elif isinstance(env_file, list):
                service_config["env_file"] = [
                    self._absolute_compose_path(challenge_dir, item)
                    for item in env_file
                ]

            volumes = service_config.get("volumes")
            if isinstance(volumes, list):
                service_config["volumes"] = [
                    self._prepare_volume_path(challenge_dir, volume)
                    for volume in volumes
                ]

        return compose_data

    def _prepare_volume_path(self, challenge_dir: Path, volume):
        if isinstance(volume, dict):
            updated = dict(volume)
            source = updated.get("source")
            volume_type = str(updated.get("type") or "")
            if isinstance(source, str) and volume_type in {"bind", ""} and source.startswith((".", "~")):
                updated["source"] = self._absolute_compose_path(challenge_dir, source)
            return updated

        if not isinstance(volume, str):
            return volume

        parts = volume.split(":")
        if not parts:
            return volume
        source = parts[0]
        if source.startswith((".", "~")):
            parts[0] = self._absolute_compose_path(challenge_dir, source)
            return ":".join(parts)
        return volume

    def _get_challenge_from_db(self, name: str) -> Optional[Challenge]:
        """Get challenge from database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, name, path, service_port, service_type, enabled,
                       access_key_hash, access_key_source, created_at
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
                access_key_hash=row["access_key_hash"] or "",
                access_key_source=row["access_key_source"] or "",
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
                ORDER BY created_at DESC, id DESC
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

    def _get_challenge_ports_from_db(self, challenge_id: int) -> list[dict]:
        """Return configured port mappings for a challenge."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT host_port, internal_port, service_type, service_name, protocol, is_primary
                FROM challenge_ports
                WHERE challenge_id = ?
                ORDER BY is_primary DESC, id ASC
            """, (challenge_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            close_db_connection(conn)

    def _runtime_port_range(self) -> tuple[int, int]:
        """Return the host port range used for runtime bindings."""
        start = int(getattr(self.config, "local_port_start", 40000) or 40000)
        end = int(getattr(self.config, "local_port_end", 49999) or 49999)
        if start > end:
            start, end = end, start
        return max(1, start), min(65535, end)

    def _running_host_ports_from_db(self, exclude_challenge_id: int | None = None) -> set[int]:
        """Return host ports already assigned to currently running challenges."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            params: list[int] = []
            challenge_filter = ""
            if exclude_challenge_id is not None:
                challenge_filter = "AND c.id != ?"
                params.append(exclude_challenge_id)

            cursor.execute(f"""
                SELECT DISTINCT cp.host_port
                FROM challenge_ports cp
                JOIN challenges c ON c.id = cp.challenge_id
                JOIN runtime_instances ri ON ri.id = (
                    SELECT id
                    FROM runtime_instances
                    WHERE challenge_id = c.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                )
                WHERE ri.status = 'running'
                {challenge_filter}
            """, params)
            return {int(row["host_port"]) for row in cursor.fetchall() if row["host_port"]}
        finally:
            close_db_connection(conn)

    def _allocate_runtime_port(self, used_ports: set[int], reserved_ports: set[int]) -> int:
        """Pick a free high host port for a challenge runtime."""
        start, end = self._runtime_port_range()
        randomize = bool(getattr(self.config, "randomize_local_ports", True))

        def available(port: int) -> bool:
            return (
                port not in used_ports
                and port not in reserved_ports
                and not is_port_in_use(port)
                and self._host_port_available_for_bind(port)
            )

        if randomize:
            attempts = min(500, max(1, end - start + 1))
            for _ in range(attempts):
                port = random.randint(start, end)
                if available(port):
                    return port

        for port in range(start, end + 1):
            if available(port):
                return port

        raise RuntimeError(f"Could not find free runtime port in range {start}-{end}")

    def _host_port_available_for_bind(self, port: int) -> bool:
        """Return True when Docker should be able to bind 0.0.0.0:port."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("0.0.0.0", int(port)))
            return True
        except OSError:
            return False

    def _is_port_bind_conflict(self, error: Exception) -> bool:
        message = str(error).lower()
        return any(
            marker in message
            for marker in (
                "address already in use",
                "failed to bind host port",
                "port is already allocated",
                "bind: address already in use",
            )
        )

    def _cleanup_failed_compose_start(self, compose_path: Path, cwd: Path, challenge_name: str) -> None:
        try:
            run_docker_compose_down_with_cleanup(
                compose_path,
                cwd=cwd,
                remove_orphans=True,
            )
        except Exception as cleanup_error:
            logger.warning(
                "Failed cleaning up partial Docker start for %s: %s",
                challenge_name,
                cleanup_error,
            )

    def _parse_compose_port_spec(self, port_spec, service_name: str = "") -> Optional[dict]:
        """Parse a compose port spec enough to remap host ports."""
        protocol = "tcp"
        host_ip = ""
        host_port = None
        internal_port = None

        if isinstance(port_spec, int):
            host_port = port_spec
            internal_port = port_spec
        elif isinstance(port_spec, str):
            raw = port_spec.strip()
            if "/" in raw:
                raw, protocol = raw.rsplit("/", 1)
            parts = raw.split(":")
            try:
                if len(parts) == 1:
                    internal_port = int(parts[0])
                    host_port = internal_port
                elif len(parts) == 2:
                    host_port = int(parts[0])
                    internal_port = int(parts[1])
                elif len(parts) >= 3:
                    host_ip = ":".join(parts[:-2])
                    host_port = int(parts[-2])
                    internal_port = int(parts[-1])
            except ValueError:
                return None
        elif isinstance(port_spec, dict):
            try:
                internal_port = int(port_spec.get("target") or 0)
                host_port = int(port_spec.get("published") or internal_port)
                host_ip = str(port_spec.get("host_ip") or "")
                protocol = str(port_spec.get("protocol") or "tcp")
            except (TypeError, ValueError):
                return None

        if not host_port or not internal_port:
            return None
        return {
            "host_ip": host_ip,
            "host_port": host_port,
            "internal_port": internal_port,
            "protocol": protocol,
            "service_name": service_name,
        }

    def _format_compose_port_spec(self, original, host_port: int):
        """Return a compose port spec with only the host port replaced."""
        if isinstance(original, int):
            return f"{host_port}:{original}"
        if isinstance(original, dict):
            updated = dict(original)
            updated["published"] = host_port
            return updated

        raw = str(original).strip()
        suffix = ""
        if "/" in raw:
            raw, protocol = raw.rsplit("/", 1)
            suffix = f"/{protocol}"
        parts = raw.split(":")
        if len(parts) == 1:
            return f"{host_port}:{parts[0]}{suffix}"
        if len(parts) == 2:
            return f"{host_port}:{parts[1]}{suffix}"
        return f"{':'.join(parts[:-2])}:{host_port}:{parts[-1]}{suffix}"

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
            # Load and modify docker-compose
            with open(docker_compose, "r", encoding="utf-8") as f:
                compose_data = yaml.safe_load(f) or {}
            compose_data = self._prepare_external_runtime_compose(compose_data, challenge_dir)

            configured_ports = extract_ports_from_compose(docker_compose)
            if not configured_ports:
                configured_ports = self._get_challenge_ports_from_db(challenge.id)
            if not configured_ports:
                configured_ports = [{
                    "host_port": challenge.service_port,
                    "internal_port": challenge.service_port,
                    "service_type": challenge.service_type,
                    "service_name": "",
                    "protocol": "tcp",
                    "is_primary": True,
                }]

            # Write modified compose to runtime state, outside the challenge cache.
            docker_compose_run = self._runtime_compose_file(challenge_name)
            docker_compose_run.parent.mkdir(parents=True, exist_ok=True)
            start_attempts = max(1, int(getattr(self.config, "runtime_start_port_attempts", 5) or 5))
            failed_ports: set[int] = set()
            last_start_error: Exception | None = None

            for attempt in range(1, start_attempts + 1):
                compose_attempt = copy.deepcopy(compose_data)
                allocated_ports = []
                used_ports = set()
                reserved_ports = self._running_host_ports_from_db(challenge.id) | failed_ports
                for index, port_info in enumerate(configured_ports):
                    desired_port = self._allocate_runtime_port(used_ports, reserved_ports)
                    used_ports.add(desired_port)
                    allocated = dict(port_info)
                    allocated["host_port"] = desired_port
                    allocated["is_primary"] = bool(port_info.get("is_primary")) or index == 0
                    allocated_ports.append(allocated)

                # Update ports in compose
                if 'services' in compose_attempt:
                    for service_name, service_config in compose_attempt['services'].items():
                        if isinstance(service_config, dict) and 'ports' in service_config:
                            new_ports = []
                            for port_spec in service_config['ports']:
                                parsed = self._parse_compose_port_spec(port_spec, service_name)
                                replacement = None
                                if parsed:
                                    for port_info in allocated_ports:
                                        if (
                                            int(port_info["internal_port"]) == int(parsed["internal_port"])
                                            and str(port_info.get("protocol") or "tcp") == str(parsed.get("protocol") or "tcp")
                                        ):
                                            replacement = self._format_compose_port_spec(port_spec, int(port_info["host_port"]))
                                            break
                                new_ports.append(replacement if replacement is not None else port_spec)
                            service_config['ports'] = new_ports

                with open(docker_compose_run, "w", encoding="utf-8") as f:
                    yaml.safe_dump(compose_attempt, f, default_flow_style=False, sort_keys=False)
                if not docker_compose_run.exists():
                    raise RuntimeError(f"Generated compose file was not created: {docker_compose_run}")

                primary_port = int(allocated_ports[0]["host_port"])
                self._replace_challenge_ports(challenge.id, allocated_ports)
                challenge.service_port = primary_port

                try:
                    logger.info(f"Starting challenge: {challenge_name} on port {primary_port}")
                    run_docker_compose_up(docker_compose_run, cwd=challenge_dir, detach=True)
                    break
                except DockerError as start_error:
                    last_start_error = start_error
                    self._cleanup_failed_compose_start(docker_compose_run, challenge_dir, challenge_name)
                    if self._is_port_bind_conflict(start_error) and attempt < start_attempts:
                        failed_ports.update(int(port["host_port"]) for port in allocated_ports)
                        logger.warning(
                            "Port bind conflict starting %s on %s; retrying with a new port (%s/%s)",
                            challenge_name,
                            ", ".join(str(port) for port in sorted(failed_ports)),
                            attempt,
                            start_attempts,
                        )
                        continue
                    raise
            else:
                raise DockerError(str(last_start_error or "Start failed"))

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
        docker_compose_run = self._runtime_compose_file(challenge_name)
        legacy_docker_compose_run = self._legacy_runtime_compose_file(challenge_dir)

        # Prefer the new runtime compose path, but keep legacy support for
        # containers started before runtime artifacts were moved out of challenge dirs.
        if docker_compose_run.exists():
            target_compose = docker_compose_run
        elif legacy_docker_compose_run.exists():
            target_compose = legacy_docker_compose_run
        else:
            target_compose = docker_compose

        if not target_compose.exists():
            raise RuntimeError(
                "No docker-compose file found. Checked: "
                f"{docker_compose_run.resolve()}, "
                f"{legacy_docker_compose_run.resolve()}, "
                f"{docker_compose.resolve()}"
            )

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

    def mark_stopped(self, challenge_name: str) -> None:
        """Mark the latest runtime stopped before external cleanup."""
        challenge = self._get_challenge_from_db(challenge_name)
        if challenge and challenge.id is not None:
            self._update_runtime_status(challenge.id, "stopped")

    def _save_runtime_to_db(self, challenge_id: int, status: str, container_id: str = "", expires_at: datetime = None) -> None:
        """Save runtime instance to database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE runtime_instances
                SET status = 'stopped'
                WHERE challenge_id = ?
                AND status = 'running'
            """, (challenge_id,))

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
                    ORDER BY created_at DESC, id DESC
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

    def _replace_challenge_ports(self, challenge_id: int, ports: list[dict]) -> None:
        """Replace stored port mappings after host-port allocation."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM challenge_ports WHERE challenge_id = ?", (challenge_id,))
            for index, port in enumerate(ports):
                cursor.execute("""
                    INSERT OR REPLACE INTO challenge_ports
                    (challenge_id, host_port, internal_port, service_type, service_name, protocol, is_primary)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    challenge_id,
                    int(port["host_port"]),
                    int(port["internal_port"]),
                    str(port.get("service_type") or "http"),
                    str(port.get("service_name") or ""),
                    str(port.get("protocol") or "tcp"),
                    1 if (port.get("is_primary") or index == 0) else 0,
                ))
            if ports:
                cursor.execute("""
                    UPDATE challenges
                    SET service_port = ?, service_type = ?
                    WHERE id = ?
                """, (
                    int(ports[0]["host_port"]),
                    str(ports[0].get("service_type") or "http"),
                    challenge_id,
                ))
            conn.commit()
        finally:
            close_db_connection(conn)
