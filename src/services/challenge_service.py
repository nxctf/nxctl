"""Challenge discovery and validation service."""

import json
import logging
from pathlib import Path
from typing import Optional

import yaml

from src.domain.models import Challenge
from src.infrastructure.database import get_db_connection, close_db_connection
from src.infrastructure.git import GitRepository

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
            for category_dir in search_dir.iterdir():
                if not category_dir.is_dir() or category_dir.name.startswith("."):
                    continue

                for challenge_dir in category_dir.iterdir():
                    if not challenge_dir.is_dir() or challenge_dir.name.startswith("."):
                        continue

                    challenge = self._extract_challenge_info(
                        challenge_dir,
                        category_dir.name,
                        repo_path
                    )
                    if challenge:
                        challenges.append(challenge)

        except Exception as e:
            raise ChallengeDiscoveryError(f"Failed to discover challenges: {str(e)}")

        return challenges

    def _extract_challenge_info(
        self,
        challenge_dir: Path,
        category: str,
        repo_root: Path
    ) -> Optional[Challenge]:
        """Extract challenge information from directory."""
        dockerfile = challenge_dir / "Dockerfile"
        docker_compose = challenge_dir / "docker-compose.yml"
        challenge_yml = challenge_dir / "challenge.yml"

        # Check if it's a valid challenge directory
        if not dockerfile.exists() and not docker_compose.exists():
            logger.debug(f"Skipping {challenge_dir} - no Dockerfile or docker-compose.yml")
            return None

        # Get challenge name (category/name)
        challenge_name = f"{category}/{challenge_dir.name}"
        challenge_path = str(challenge_dir.relative_to(repo_root)).replace("\\", "/")

        # Extract port information
        service_port = self._extract_port(challenge_dir)
        service_type = self._detect_service_type(challenge_dir)

        challenge = Challenge(
            name=challenge_name,
            path=challenge_path,
            service_port=service_port,
            service_type=service_type,
        )

        logger.info(f"Discovered challenge: {challenge_name} (port {service_port}, type {service_type})")
        return challenge

    def _extract_port(self, challenge_dir: Path) -> int:
        """Extract service port from Docker config."""
        docker_compose = challenge_dir / "docker-compose.yml"

        if docker_compose.exists():
            try:
                with open(docker_compose, "r") as f:
                    config = yaml.safe_load(f) or {}

                services = config.get("services", {})
                for service_name, service_config in services.items():
                    if isinstance(service_config, dict):
                        ports = service_config.get("ports", [])
                        if ports:
                            # Extract first port
                            first_port = ports[0]
                            if isinstance(first_port, str):
                                # Format: "8080" or "8080:8080"
                                container_port = first_port.split(":")[-1].strip()
                                try:
                                    return int(container_port)
                                except ValueError:
                                    pass
                            elif isinstance(first_port, int):
                                return first_port

            except Exception as e:
                logger.warning(f"Failed to extract port from {docker_compose}: {str(e)}")

        # Default port
        return 8080

    def _detect_service_type(self, challenge_dir: Path) -> str:
        """Detect service type (http/tcp)."""
        docker_compose = challenge_dir / "docker-compose.yml"

        if docker_compose.exists():
            try:
                with open(docker_compose, "r") as f:
                    config = yaml.safe_load(f) or {}

                # Look for environment variables that might indicate type
                services = config.get("services", {})
                for service_config in services.values():
                    if isinstance(service_config, dict):
                        env = service_config.get("environment", {})
                        if isinstance(env, dict):
                            service_type = env.get("SERVICE_TYPE") or env.get("service_type")
                            if service_type:
                                return str(service_type).lower()

            except Exception:
                pass

        # Default: HTTP
        return "http"

    def sync_challenges(
        self,
        git_repo: GitRepository,
        challenge_base_dir: str = ""
    ) -> list[Challenge]:
        """Sync challenges from Git repository."""
        logger.info(f"Syncing challenges from {git_repo.repo_url}")

        # Ensure repository is cloned/updated
        git_repo.pull() if git_repo.local_path.exists() else git_repo.clone()

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
        """Get challenge by name."""
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
