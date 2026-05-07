"""YAML parsing and utilities."""

import logging
from pathlib import Path
from typing import Optional, Any, Dict

import yaml

logger = logging.getLogger(__name__)


def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load YAML file, return empty dict if not found."""
    if not file_path.exists():
        logger.debug(f"YAML file not found: {file_path}")
        return {}

    try:
        with open(file_path, "r") as f:
            content = yaml.safe_load(f)
            return content or {}
    except Exception as e:
        logger.error(f"Failed to parse YAML file {file_path}: {e}")
        return {}


def extract_port_from_compose(compose_path: Path) -> int:
    """Extract service port from docker-compose.yml."""
    config = load_yaml_file(compose_path)

    if not config:
        return 8080

    try:
        services = config.get("services", {})

        for service_name, service_config in services.items():
            if isinstance(service_config, dict):
                ports = service_config.get("ports", [])

                if ports:
                    first_port = ports[0]

                    if isinstance(first_port, str):
                        # Format: "8080" or "8080:8080"
                        parts = first_port.split(":")
                        container_port = parts[-1].strip()
                        try:
                            return int(container_port)
                        except ValueError:
                            continue
                    elif isinstance(first_port, int):
                        return first_port

    except Exception as e:
        logger.warning(f"Failed to extract port from {compose_path}: {e}")

    return 8080


def detect_service_type_from_compose(compose_path: Path) -> str:
    """Detect service type (http/tcp) from docker-compose.yml."""
    config = load_yaml_file(compose_path)

    if not config:
        return "http"

    try:
        services = config.get("services", {})

        for service_config in services.values():
            if isinstance(service_config, dict):
                # Check environment variables
                env = service_config.get("environment", {})

                if isinstance(env, dict):
                    service_type = env.get("SERVICE_TYPE") or env.get("service_type")
                    if service_type:
                        return str(service_type).lower()
                elif isinstance(env, list):
                    # Environment can be a list of KEY=VALUE strings
                    for env_var in env:
                        if env_var.startswith("SERVICE_TYPE="):
                            return env_var.split("=", 1)[1].lower()

    except Exception as e:
        logger.warning(f"Failed to detect service type from {compose_path}: {e}")

    return "http"
