"""Shared base utilities for CLI command handlers."""

import logging
from src.core.config import get_config
from src.core.db import init_database
from src.core.utils import (
    green, red, yellow, blue, bold,
    get_git_cache_path,
    get_challenge_dir
)
from src.core.yaml import extract_port_from_compose
from src.scripts.challenge_service import ChallengeService
from src.scripts.runtime_service import RuntimeService
from src.scripts.exports.manager import ExportManager

logger = logging.getLogger(__name__)


def get_container_port(config, challenge) -> str:
    """Helper to extract container port using core utilities."""
    challenge_dir = get_challenge_dir(challenge.path)
    docker_compose = challenge_dir / "docker-compose.yml"
    return str(extract_port_from_compose(docker_compose))


def get_services():
    """Initialize and return all core services."""
    config = get_config()
    init_database(config.db_file)
    challenge_service = ChallengeService(config.db_file)
    runtime_service = RuntimeService(config, config.db_file, get_git_cache_path())
    export_manager = ExportManager(config, config.db_file)
    return config, challenge_service, runtime_service, export_manager
