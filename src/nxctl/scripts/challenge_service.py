"""Challenge discovery and management service."""

import logging
from pathlib import Path
from typing import Optional

from nxctl.core.access import hash_access_key
from nxctl.core.challenge_config import load_inherited_challenge_config
from nxctl.core.models import Challenge, ChallengePort
from nxctl.core.db import get_db_connection, close_db_connection
from nxctl.core.git import GitRepository
from nxctl.core.yaml import extract_ports_from_compose

logger = logging.getLogger(__name__)


class ChallengeDiscoveryError(Exception):
    """Challenge discovery error."""
    pass


class ChallengeService:
    """Service for managing challenges."""

    def __init__(self, db_path: str):
        """Initialize challenge service."""
        self.db_path = db_path
        self.last_sync_disabled_stale_count = 0

    def discover_challenges(
        self,
        repo_path: Path,
        challenge_base_dir: str = ""
    ) -> list[Challenge]:
        """Discover challenges from repository."""
        challenges = []
        search_dir = repo_path / challenge_base_dir if challenge_base_dir else repo_path

        try:
            candidate_dirs = self._find_candidate_challenge_dirs(search_dir)

            for challenge_dir in candidate_dirs:
                challenge = self._extract_challenge_info(challenge_dir, repo_path)
                if challenge:
                    challenges.append(challenge)

        except Exception as e:
            raise ChallengeDiscoveryError(f"Failed to discover challenges: {str(e)}")

        return challenges

    def _find_candidate_challenge_dirs(self, search_dir: Path) -> list[Path]:
        """Find directories that look like challenge roots."""
        compose_dirs = set()
        dockerfile_dirs = set()

        for compose_path in search_dir.rglob("docker-compose.yml"):
            if self._is_hidden_path(compose_path, search_dir):
                continue
            compose_dirs.add(compose_path.parent)

        for dockerfile_path in search_dir.rglob("Dockerfile"):
            if self._is_hidden_path(dockerfile_path, search_dir):
                continue

            dockerfile_dir = dockerfile_path.parent
            if any(compose_dir in dockerfile_dir.parents or compose_dir == dockerfile_dir for compose_dir in compose_dirs):
                continue
            dockerfile_dirs.add(dockerfile_dir)

        candidates = compose_dirs | dockerfile_dirs
        return sorted(candidates, key=lambda path: str(path.relative_to(search_dir)).replace("\\", "/"))

    def _is_hidden_path(self, path: Path, search_dir: Path) -> bool:
        """Return True when the path is inside a hidden directory."""
        try:
            relative_parts = path.relative_to(search_dir).parts
        except ValueError:
            relative_parts = path.parts

        return any(part.startswith(".") for part in relative_parts)

    def _extract_challenge_info(
        self,
        challenge_dir: Path,
        repo_root: Path
    ) -> Optional[Challenge]:
        """Extract challenge information from directory."""
        dockerfile = challenge_dir / "Dockerfile"
        docker_compose = challenge_dir / "docker-compose.yml"

        # Check if it's a valid challenge directory
        if not dockerfile.exists() and not docker_compose.exists():
            logger.debug(f"Skipping {challenge_dir} - no Dockerfile or docker-compose.yml")
            return None

        # Use the relative path from repo root as the challenge name.
        challenge_name = str(challenge_dir.relative_to(repo_root)).replace("\\", "/")
        challenge_path = str(challenge_dir.relative_to(repo_root)).replace("\\", "/")
        local_config = load_inherited_challenge_config(challenge_dir, repo_root)
        access_key_hash = hash_access_key(local_config.key)
        access_key_source = local_config.key_source if access_key_hash else ""

        # Extract port and service type information
        service_port = 0
        service_type = "http"

        if docker_compose.exists():
            port_bindings = extract_ports_from_compose(docker_compose)
            if port_bindings:
                service_port = int(port_bindings[0]["host_port"])
                service_type = str(port_bindings[0]["service_type"])

        challenge = Challenge(
            name=challenge_name,
            path=challenge_path,
            service_port=service_port,
            service_type=service_type,
            enabled=True if local_config.enabled is None else local_config.enabled,
            access_key_hash=access_key_hash,
            access_key_source=access_key_source,
            config_source=", ".join(local_config.config_sources),
            ttl_default_minutes=local_config.ttl.get("default_minutes"),
            ttl_extend_minutes=local_config.ttl.get("extend_minutes"),
            ttl_extend_threshold_minutes=local_config.ttl.get("extend_threshold_minutes"),
            ttl_extend_cooldown_seconds=local_config.ttl.get("extend_cooldown_seconds"),
            can_restart=local_config.can_restart,
            restart_cooldown_seconds=local_config.restart_cooldown_seconds,
        )

        logger.info(f"Discovered challenge: {challenge_name} (port {service_port}, type {service_type})")
        return challenge

    def sync_challenges(
        self,
        git_repo: GitRepository,
        challenge_base_dir: str = ""
    ) -> list[Challenge]:
        """Sync challenges from Git repository."""
        logger.info(f"Syncing challenges from {git_repo.repo_url}")

        # Ensure repository is cloned/updated
        # If the cache path is a valid git work tree, pull updates; otherwise clone.
        if git_repo._is_git_repository(git_repo.local_path):
            git_repo.pull()
        else:
            git_repo.clone()

        # Discover challenges
        challenges = self.discover_challenges(git_repo.local_path, challenge_base_dir)

        # Save to database
        self._save_challenges_to_db(challenges, challenge_base_dir)

        logger.info(f"Synced {len(challenges)} challenges")
        return challenges

    def _save_challenges_to_db(
        self,
        challenges: list[Challenge],
        challenge_base_dir: str = "",
    ) -> None:
        """Save challenges to database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            discovered_names = {challenge.name for challenge in challenges}
            for challenge in challenges:
                cursor.execute("""
                    INSERT INTO challenges
                    (
                        name, path, service_port, service_type, enabled,
                        access_key_hash, access_key_source, config_source,
                        ttl_default_minutes, ttl_extend_minutes,
                        ttl_extend_threshold_minutes, ttl_extend_cooldown_seconds,
                        can_restart, restart_cooldown_seconds
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        path = excluded.path,
                        service_port = excluded.service_port,
                        service_type = excluded.service_type,
                        enabled = excluded.enabled,
                        access_key_hash = excluded.access_key_hash,
                        access_key_source = excluded.access_key_source,
                        config_source = excluded.config_source,
                        ttl_default_minutes = excluded.ttl_default_minutes,
                        ttl_extend_minutes = excluded.ttl_extend_minutes,
                        ttl_extend_threshold_minutes = excluded.ttl_extend_threshold_minutes,
                        ttl_extend_cooldown_seconds = excluded.ttl_extend_cooldown_seconds,
                        can_restart = excluded.can_restart,
                        restart_cooldown_seconds = excluded.restart_cooldown_seconds
                """, (
                    challenge.name,
                    challenge.path,
                    challenge.service_port,
                    challenge.service_type,
                    challenge.enabled,
                    challenge.access_key_hash,
                    challenge.access_key_source,
                    challenge.config_source,
                    challenge.ttl_default_minutes,
                    challenge.ttl_extend_minutes,
                    challenge.ttl_extend_threshold_minutes,
                    challenge.ttl_extend_cooldown_seconds,
                    challenge.can_restart,
                    challenge.restart_cooldown_seconds,
                ))
                cursor.execute("SELECT id FROM challenges WHERE name = ?", (challenge.name,))
                row = cursor.fetchone()
                if row:
                    self._save_ports_for_challenge(cursor, int(row["id"]), challenge)

            self.last_sync_disabled_stale_count = self._disable_stale_challenges(
                cursor,
                discovered_names,
                challenge_base_dir,
            )
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to save challenges: {str(e)}")
        finally:
            close_db_connection(conn)

    def _disable_stale_challenges(
        self,
        cursor,
        discovered_names: set[str],
        challenge_base_dir: str = "",
    ) -> int:
        """Disable DB challenges no longer discovered by sync."""
        where_parts = ["enabled = 1"]
        params: list[str] = []

        normalized_base = str(challenge_base_dir or "").replace("\\", "/").strip("/")
        if normalized_base:
            where_parts.append("(name = ? OR name LIKE ?)")
            params.extend([normalized_base, f"{normalized_base}/%"])

        if discovered_names:
            placeholders = ", ".join("?" for _ in discovered_names)
            where_parts.append(f"name NOT IN ({placeholders})")
            params.extend(sorted(discovered_names))

        cursor.execute(
            f"""
                SELECT id
                FROM challenges
                WHERE {' AND '.join(where_parts)}
            """,
            params,
        )
        stale_ids = [int(row["id"]) for row in cursor.fetchall()]
        if not stale_ids:
            return 0

        stale_placeholders = ", ".join("?" for _ in stale_ids)
        cursor.execute(
            f"""
                UPDATE challenges
                SET enabled = 0,
                    access_key_hash = '',
                    access_key_source = '',
                    config_source = '',
                    ttl_default_minutes = NULL,
                    ttl_extend_minutes = NULL,
                    ttl_extend_threshold_minutes = NULL,
                    ttl_extend_cooldown_seconds = NULL,
                    can_restart = NULL,
                    restart_cooldown_seconds = NULL
                WHERE id IN ({stale_placeholders})
            """,
            stale_ids,
        )
        cursor.execute(
            f"DELETE FROM challenge_ports WHERE challenge_id IN ({stale_placeholders})",
            stale_ids,
        )
        return len(stale_ids)

    def _save_ports_for_challenge(self, cursor, challenge_id: int, challenge: Challenge) -> None:
        """Save all compose port mappings for a challenge."""
        ports = []
        try:
            from nxctl.core.utils import get_challenge_dir
            ports = extract_ports_from_compose(get_challenge_dir(challenge.path) / "docker-compose.yml")
        except Exception:
            ports = []

        if not ports and challenge.service_port:
            ports = [{
                "host_port": challenge.service_port,
                "internal_port": challenge.service_port,
                "service_type": challenge.service_type,
                "service_name": "",
                "protocol": "tcp",
            }]

        cursor.execute(
            "SELECT id FROM runtime_instances WHERE challenge_id = ? AND status = 'running'",
            (challenge_id,),
        )
        if cursor.fetchone():
            logger.debug(f"Preserving active runtime ports for challenge_id={challenge_id}")
            return

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
                str(port["service_type"]),
                str(port.get("service_name") or ""),
                str(port.get("protocol") or "tcp"),
                1 if index == 0 else 0,
            ))

    def list_challenges(self, include_disabled: bool = False) -> list[Challenge]:
        """List all challenges from database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            enabled_filter = "" if include_disabled else "WHERE enabled = 1"
            cursor.execute("""
                SELECT id, name, path, service_port, service_type, enabled,
                       access_key_hash, access_key_source, config_source,
                       ttl_default_minutes, ttl_extend_minutes,
                       ttl_extend_threshold_minutes, ttl_extend_cooldown_seconds,
                       can_restart, restart_cooldown_seconds, created_at
                FROM challenges
                {enabled_filter}
                ORDER BY name
            """.format(enabled_filter=enabled_filter))

            challenges = []
            for row in cursor.fetchall():
                challenges.append(self._challenge_from_row(row))

            return challenges

        finally:
            close_db_connection(conn)

    def list_challenge_ports(self, name: str) -> list[ChallengePort]:
        """List all configured port mappings for a challenge."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT cp.id, cp.challenge_id, cp.host_port, cp.internal_port,
                       cp.service_type, cp.service_name, cp.protocol, cp.is_primary
                FROM challenge_ports cp
                JOIN challenges c ON c.id = cp.challenge_id
                WHERE c.name = ?
                ORDER BY cp.is_primary DESC, cp.id ASC
            """, (name,))
            ports = [
                ChallengePort(
                    id=row["id"],
                    challenge_id=row["challenge_id"],
                    host_port=row["host_port"],
                    internal_port=row["internal_port"],
                    service_type=row["service_type"],
                    service_name=row["service_name"] or "",
                    protocol=row["protocol"] or "tcp",
                    is_primary=bool(row["is_primary"]),
                )
                for row in cursor.fetchall()
            ]

            if ports:
                return ports

            challenge = self.get_challenge(name)
            if not challenge or not challenge.service_port:
                return []
            return [ChallengePort(
                challenge_id=challenge.id or 0,
                host_port=challenge.service_port,
                internal_port=challenge.service_port,
                service_type=challenge.service_type,
                is_primary=True,
            )]
        finally:
            close_db_connection(conn)

    def list_challenges_under(
        self,
        prefix: Optional[str] = None,
        include_disabled: bool = False,
    ) -> list[Challenge]:
        """List challenges at or below a normalized repository path prefix."""
        challenges = self.list_challenges(include_disabled=include_disabled)
        if prefix is None:
            return challenges

        normalized = str(prefix).replace("\\", "/").strip("/")
        if not normalized:
            return challenges
        if any(part in {".", ".."} for part in normalized.split("/")):
            raise ValueError(f"Invalid challenge prefix: {prefix}")

        subtree_prefix = f"{normalized}/"
        return [
            challenge
            for challenge in challenges
            if challenge.name == normalized or challenge.name.startswith(subtree_prefix)
        ]

    def get_challenge(self, name: str) -> Optional[Challenge]:
        """Get a single challenge by exact name or partial match."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, name, path, service_port, service_type, enabled,
                       access_key_hash, access_key_source, config_source,
                       ttl_default_minutes, ttl_extend_minutes,
                       ttl_extend_threshold_minutes, ttl_extend_cooldown_seconds,
                       can_restart, restart_cooldown_seconds, created_at
                FROM challenges
                WHERE name = ?
            """, (name,))

            row = cursor.fetchone()
            if row:
                return self._challenge_from_row(row)

            cursor.execute("""
                SELECT id, name, path, service_port, service_type, enabled,
                       access_key_hash, access_key_source, config_source,
                       ttl_default_minutes, ttl_extend_minutes,
                       ttl_extend_threshold_minutes, ttl_extend_cooldown_seconds,
                       can_restart, restart_cooldown_seconds, created_at
                FROM challenges
                WHERE name LIKE ? OR name LIKE ? OR name LIKE ?
            """, (f"{name}%", f"%/{name}%", f"%{name}%"))

            rows = cursor.fetchall()
            if len(rows) == 1:
                return self._challenge_from_row(rows[0])
            elif len(rows) > 1:
                prefix_matches = [r for r in rows if r["name"].startswith(name)]
                if len(prefix_matches) == 1:
                    return self._challenge_from_row(prefix_matches[0])

            return None

        finally:
            close_db_connection(conn)

    def _challenge_from_row(self, row) -> Challenge:
        """Build a Challenge model from a SQLite row."""
        return Challenge(
            id=row["id"],
            name=row["name"],
            path=row["path"],
            service_port=row["service_port"],
            service_type=row["service_type"],
            enabled=bool(row["enabled"]),
            access_key_hash=row["access_key_hash"] or "",
            access_key_source=row["access_key_source"] or "",
            config_source=row["config_source"] or "",
            ttl_default_minutes=row["ttl_default_minutes"],
            ttl_extend_minutes=row["ttl_extend_minutes"],
            ttl_extend_threshold_minutes=row["ttl_extend_threshold_minutes"],
            ttl_extend_cooldown_seconds=row["ttl_extend_cooldown_seconds"],
            can_restart=None if row["can_restart"] is None else bool(row["can_restart"]),
            restart_cooldown_seconds=row["restart_cooldown_seconds"],
            created_at=row["created_at"],
        )

    def add_challenge(self, name: str, path: str, port: int, service_type: str = "http") -> Challenge:
        """Add a challenge manually."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO challenges (name, path, service_port, service_type, enabled)
                VALUES (?, ?, ?, ?, ?)
            """, (name, path, port, service_type, True))

            conn.commit()
            challenge_id = cursor.lastrowid
            self._save_ports_for_challenge(cursor, challenge_id, Challenge(
                id=challenge_id,
                name=name,
                path=path,
                service_port=port,
                service_type=service_type,
                enabled=True,
            ))
            conn.commit()

            return Challenge(
                id=challenge_id,
                name=name,
                path=path,
                service_port=port,
                service_type=service_type,
                enabled=True,
            )

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to add challenge: {str(e)}")
        finally:
            close_db_connection(conn)

    def remove_challenge(self, name: str, runtime_service=None, export_manager=None, config=None) -> bool:
        """Remove a challenge."""
        # 1. Fetch challenge info first to stop it and find its path/id
        challenge = self.get_challenge(name)
        if not challenge:
            return False

        # 2. Stop containers and exports if services are provided
        if runtime_service and export_manager:
            try:
                from nxctl.scripts.cli.lifecycle import _stop_challenge_completely
                _stop_challenge_completely(name, self, runtime_service, export_manager)
            except Exception as stop_exc:
                logger.warning(f"Failed to stop challenge {name} before removing: {stop_exc}")

        # 3. Clean filesystem artifacts if config is provided
        if config:
            from nxctl.core.utils import safe_runtime_name
            # Source cache folder
            if challenge.path:
                try:
                    chall_dir = Path(config.chall_dir).resolve()
                    challenge_dir = (chall_dir / challenge.path).resolve()
                    if challenge_dir.exists() and challenge_dir != chall_dir and challenge_dir.is_relative_to(chall_dir):
                        import shutil
                        shutil.rmtree(challenge_dir, ignore_errors=True)
                        logger.info(f"Deleted source cache directory: {challenge_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete source cache directory for {name}: {e}")
            # Generated docker-compose file
            try:
                compose_file = (Path(config.compose_dir) / f"{safe_runtime_name(name)}.docker-compose.yml").resolve()
                if compose_file.is_file():
                    compose_file.unlink(missing_ok=True)
                    logger.info(f"Deleted generated compose file: {compose_file}")
            except Exception as e:
                logger.warning(f"Failed to delete generated compose file for {name}: {e}")
            # Lock file
            try:
                lock_file = (Path(config.locks_dir) / f"{safe_runtime_name(name)}.lock").resolve()
                if lock_file.is_file():
                    lock_file.unlink(missing_ok=True)
                    logger.info(f"Deleted lock file: {lock_file}")
            except Exception as e:
                logger.warning(f"Failed to delete lock file for {name}: {e}")

        # 4. Perform database deletion
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # Delete ports for this challenge
            cursor.execute("DELETE FROM challenge_ports WHERE challenge_id = ?", (challenge.id,))
            # Delete exports for this challenge
            cursor.execute("DELETE FROM challenge_exports WHERE runtime_id IN (SELECT id FROM runtime_instances WHERE challenge_id = ?)", (challenge.id,))
            # Delete runtime instances
            cursor.execute("DELETE FROM runtime_instances WHERE challenge_id = ?", (challenge.id,))
            # Delete the challenge itself
            cursor.execute("DELETE FROM challenges WHERE id = ?", (challenge.id,))
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to remove challenge: {str(e)}")
        finally:
            close_db_connection(conn)

    def prune_disabled_challenges(self, runtime_service=None, export_manager=None, config=None, all_challenges: bool = False) -> int:
        """Remove disabled (or all) challenges and their associated records from the database and filesystem."""
        if all_challenges:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, name, path FROM challenges")
                rows = cursor.fetchall()
                count = len(rows)

                # 1. Stop all challenges completely
                for row in rows:
                    name = str(row["name"])
                    if runtime_service and export_manager:
                        try:
                            from nxctl.scripts.cli.lifecycle import _stop_challenge_completely
                            _stop_challenge_completely(name, self, runtime_service, export_manager)
                        except Exception as stop_exc:
                            logger.warning(f"Failed to stop challenge {name} before purging: {stop_exc}")
            finally:
                close_db_connection(conn)

            # 2. Delete filesystem artifacts if config is provided
            if config:
                import shutil
                # Delete chall_dir
                try:
                    chall_dir = Path(config.chall_dir).resolve()
                    if chall_dir.exists():
                        shutil.rmtree(chall_dir, ignore_errors=True)
                        logger.info(f"Deleted chall_dir: {chall_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete chall_dir: {e}")

                # Delete runtime_dir
                try:
                    runtime_dir = Path(config.runtime_dir).resolve()
                    if runtime_dir.exists():
                        shutil.rmtree(runtime_dir, ignore_errors=True)
                        logger.info(f"Deleted runtime_dir: {runtime_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete runtime_dir: {e}")

                # Delete db_file
                try:
                    db_file = Path(config.db_file).resolve()
                    if db_file.exists():
                        db_file.unlink(missing_ok=True)
                        logger.info(f"Deleted db_file: {db_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete db_file: {e}")
            else:
                # Fallback database deletion for tests if config is not passed
                conn = get_db_connection(self.db_path)
                cursor = conn.cursor()
                try:
                    cursor.execute("DELETE FROM challenge_ports")
                    cursor.execute("DELETE FROM challenge_exports")
                    cursor.execute("DELETE FROM runtime_instances")
                    cursor.execute("DELETE FROM challenges")
                    conn.commit()
                finally:
                    close_db_connection(conn)

            return count

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT id, name, path FROM challenges WHERE enabled = 0")
            disabled_rows = cursor.fetchall()
            if not disabled_rows:
                return 0

            disabled_challenges = []
            disabled_ids = []
            for row in disabled_rows:
                disabled_ids.append(int(row["id"]))
                disabled_challenges.append({
                    "id": int(row["id"]),
                    "name": str(row["name"]),
                    "path": str(row["path"] or ""),
                })

            # Stop challenges and cleanup exports/containers
            for chall in disabled_challenges:
                name = chall["name"]
                if runtime_service and export_manager:
                    try:
                        from nxctl.scripts.cli.lifecycle import _stop_challenge_completely
                        _stop_challenge_completely(name, self, runtime_service, export_manager)
                    except Exception as stop_exc:
                        logger.warning(f"Failed to stop disabled challenge {name} before pruning: {stop_exc}")

                # Clean filesystem artifacts if config is provided
                if config:
                    from nxctl.core.utils import safe_runtime_name
                    # Source cache folder
                    if chall["path"]:
                        try:
                            chall_dir = Path(config.chall_dir).resolve()
                            challenge_dir = (chall_dir / chall["path"]).resolve()
                            if challenge_dir.exists() and challenge_dir != chall_dir and challenge_dir.is_relative_to(chall_dir):
                                import shutil
                                shutil.rmtree(challenge_dir, ignore_errors=True)
                                logger.info(f"Deleted source cache directory: {challenge_dir}")
                        except Exception as e:
                            logger.warning(f"Failed to delete source cache directory for {name}: {e}")
                    # Generated docker-compose file
                    try:
                        compose_file = (Path(config.compose_dir) / f"{safe_runtime_name(name)}.docker-compose.yml").resolve()
                        if compose_file.is_file():
                            compose_file.unlink(missing_ok=True)
                            logger.info(f"Deleted generated compose file: {compose_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete generated compose file for {name}: {e}")
                    # Lock file
                    try:
                        lock_file = (Path(config.locks_dir) / f"{safe_runtime_name(name)}.lock").resolve()
                        if lock_file.is_file():
                            lock_file.unlink(missing_ok=True)
                            logger.info(f"Deleted lock file: {lock_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete lock file for {name}: {e}")

            placeholders = ", ".join("?" for _ in disabled_ids)
            # Delete ports for these challenges
            cursor.execute(f"DELETE FROM challenge_ports WHERE challenge_id IN ({placeholders})", disabled_ids)
            # Delete exports for these challenges
            cursor.execute(f"DELETE FROM challenge_exports WHERE runtime_id IN (SELECT id FROM runtime_instances WHERE challenge_id IN ({placeholders}))", disabled_ids)
            # Delete runtime instances
            cursor.execute(f"DELETE FROM runtime_instances WHERE challenge_id IN ({placeholders})", disabled_ids)
            # Delete the challenges themselves
            cursor.execute(f"DELETE FROM challenges WHERE id IN ({placeholders})", disabled_ids)
            
            conn.commit()
            return len(disabled_ids)

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to prune challenges: {str(e)}")
        finally:
            close_db_connection(conn)
