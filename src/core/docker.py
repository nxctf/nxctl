"""Docker and Docker Compose utilities."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DockerError(Exception):
    """Docker operation error."""
    pass


def run_docker_compose_build(compose_path: Path, cwd: Optional[Path] = None, timeout: int = 300) -> str:
    """Build Docker image using docker compose.

    Tries docker compose v2 first, falls back to v1.

    Returns:
        Image name (e.g., "challenge-name:latest")
    """
    if not compose_path.exists():
        raise DockerError(f"docker-compose.yml not found: {compose_path}")

    cwd = cwd or compose_path.parent

    logger.info(f"Building image from {compose_path}")

    try:
        # Try docker compose v2 first
        cmd = ["docker", "compose", "-f", str(compose_path), "build"]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            logger.info(f"Successfully built image using docker compose v2")
            return "latest"
        except FileNotFoundError:
            # Fall back to docker-compose v1
            logger.info("docker compose v2 not found, trying docker-compose v1...")
            cmd = ["docker-compose", "-f", str(compose_path), "build"]
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            logger.info(f"Successfully built image using docker-compose v1")
            return "latest"

    except subprocess.TimeoutExpired:
        raise DockerError("Build operation timed out")
    except subprocess.CalledProcessError as e:
        raise DockerError(f"Build failed: {e.stderr}")
    except Exception as e:
        raise DockerError(f"Build failed: {str(e)}")


def run_docker_compose_up(compose_path: Path, cwd: Optional[Path] = None, detach: bool = True) -> dict:
    """Start containers using docker compose.

    Returns:
        Dict with container info
    """
    if not compose_path.exists():
        raise DockerError(f"docker-compose.yml not found: {compose_path}")

    cwd = cwd or compose_path.parent

    logger.info(f"Starting containers from {compose_path}")

    try:
        cmd = ["docker", "compose", "-f", str(compose_path), "up"]
        if detach:
            cmd.append("-d")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except FileNotFoundError:
            # Fall back to docker-compose v1
            cmd = ["docker-compose", "-f", str(compose_path), "up"]
            if detach:
                cmd.append("-d")

            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

        logger.info(f"Successfully started containers")
        return {"status": "success"}

    except subprocess.TimeoutExpired:
        raise DockerError("Start operation timed out")
    except subprocess.CalledProcessError as e:
        raise DockerError(f"Start failed: {e.stderr}")
    except Exception as e:
        raise DockerError(f"Start failed: {str(e)}")


def run_docker_compose_down(compose_path: Path, cwd: Optional[Path] = None) -> dict:
    """Stop containers using docker compose."""
    if not compose_path.exists():
        raise DockerError(f"docker-compose.yml not found: {compose_path}")

    cwd = cwd or compose_path.parent

    logger.info(f"Stopping containers from {compose_path}")

    try:
        cmd = ["docker", "compose", "-f", str(compose_path), "down"]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except FileNotFoundError:
            # Fall back to docker-compose v1
            cmd = ["docker-compose", "-f", str(compose_path), "down"]
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

        logger.info(f"Successfully stopped containers")
        return {"status": "success"}

    except subprocess.TimeoutExpired:
        raise DockerError("Stop operation timed out")
    except subprocess.CalledProcessError as e:
        raise DockerError(f"Stop failed: {e.stderr}")
    except Exception as e:
        raise DockerError(f"Stop failed: {str(e)}")


def get_running_containers_for_challenge(challenge_name: str) -> list[str]:
    """Get list of running container IDs for a challenge."""
    try:
        cmd = ["docker", "ps", "-q", "-f", f"label=challenge={challenge_name}"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return [cid.strip() for cid in result.stdout.strip().split("\n") if cid.strip()]
    except Exception as e:
        logger.warning(f"Failed to get containers for {challenge_name}: {e}")
        return []
