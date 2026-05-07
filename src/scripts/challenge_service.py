"""Challenge discovery and management service."""

import logging
from pathlib import Path
from typing import Optional

from src.core.models import Challenge
from src.core.db import get_db_connection, close_db_connection
from src.core.git import GitRepository
from src.core.yaml import extract_port_from_compose, detect_service_type_from_compose

logger = logging.getLogger(__name__)


class ChallengeDiscoveryError(Exception):
    """Challenge discovery error."""
    pass


class ChallengeService:
    """Service for managing challenges."""

    def __init__(self, db_path: str):
        """Initialize challenge service."""
        self.db_path = db_path

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

        # Extract port and service type information
        service_port = 8080
        service_type = "http"

        if docker_compose.exists():
            service_port = extract_port_from_compose(docker_compose)
            service_type = detect_service_type_from_compose(docker_compose)

        challenge = Challenge(
            name=challenge_name,
            path=challenge_path,
            service_port=service_port,
            service_type=service_type,
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
        self._save_challenges_to_db(challenges)

        logger.info(f"Synced {len(challenges)} challenges")
        return challenges

    def _save_challenges_to_db(self, challenges: list[Challenge]) -> None:
        """Save challenges to database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            for challenge in challenges:
                cursor.execute("""
                    INSERT OR REPLACE INTO challenges
                    (name, path, service_port, service_type, enabled)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    challenge.name,
                    challenge.path,
                    challenge.service_port,
                    challenge.service_type,
                    challenge.enabled,
                ))

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to save challenges: {str(e)}")
        finally:
            close_db_connection(conn)

    def list_challenges(self) -> list[Challenge]:
        """List all challenges from database."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, name, path, service_port, service_type, enabled, created_at
                FROM challenges
                ORDER BY name
            """)

            challenges = []
            for row in cursor.fetchall():
                challenge = Challenge(
                    id=row["id"],
                    name=row["name"],
                    path=row["path"],
                    service_port=row["service_port"],
                    service_type=row["service_type"],
                    enabled=bool(row["enabled"]),
                    created_at=row["created_at"],
                )
                challenges.append(challenge)

            return challenges

        finally:
            close_db_connection(conn)

    def get_challenge(self, name: str) -> Optional[Challenge]:
        """Get a single challenge by name."""
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

    def remove_challenge(self, name: str) -> bool:
        """Remove a challenge."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM challenges WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to remove challenge: {str(e)}")
        finally:
            close_db_connection(conn)

    def enable_challenge(self, name: str) -> bool:
        """Enable a challenge."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("UPDATE challenges SET enabled = 1 WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to enable challenge: {str(e)}")
        finally:
            close_db_connection(conn)

    def disable_challenge(self, name: str) -> bool:
        """Disable a challenge."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("UPDATE challenges SET enabled = 0 WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise ChallengeDiscoveryError(f"Failed to disable challenge: {str(e)}")
        finally:
            close_db_connection(conn)
