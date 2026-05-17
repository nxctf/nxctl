"""YAML parsing and utilities."""

import logging
from pathlib import Path
from typing import Optional, Any, Dict

import yaml

logger = logging.getLogger(__name__)

HTTP_COMMON_PORTS = {80, 443, 8000, 8080}


def infer_service_type(port: int) -> str:
    return "http" if int(port) in HTTP_COMMON_PORTS else "tcp"


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


def _parse_port_spec(port_spec: Any, service_name: str = "") -> Optional[dict]:
    """Parse a compose port entry into host/internal/service metadata."""
    protocol = "tcp"
    host_port = None
    internal_port = None

    if isinstance(port_spec, int):
        host_port = port_spec
        internal_port = port_spec
    elif isinstance(port_spec, str):
        raw = port_spec.strip()
        if "/" in raw:
            raw, protocol = raw.rsplit("/", 1)
            protocol = protocol.strip() or "tcp"
        parts = raw.split(":")
        try:
            if len(parts) == 1:
                internal_port = int(parts[0])
                host_port = internal_port
            elif len(parts) >= 2:
                internal_port = int(parts[-1])
                host_port = int(parts[-2])
        except ValueError:
            return None
    elif isinstance(port_spec, dict):
        try:
            internal_port = int(port_spec.get("target") or port_spec.get("container") or 0)
            published = port_spec.get("published") or port_spec.get("host_port") or internal_port
            host_port = int(published)
            protocol = str(port_spec.get("protocol") or "tcp")
        except (TypeError, ValueError):
            return None

    if not host_port or not internal_port:
        return None

    return {
        "host_port": host_port,
        "internal_port": internal_port,
        "service_type": infer_service_type(internal_port),
        "service_name": service_name,
        "protocol": protocol,
    }


def extract_ports_from_compose(compose_path: Path) -> list[dict]:
    """Extract all published ports from docker-compose.yml."""
    config = load_yaml_file(compose_path)
    if not config:
        return []

    ports: list[dict] = []
    try:
        services = config.get("services", {})
        for service_name, service_config in services.items():
            if not isinstance(service_config, dict):
                continue

            service_type_override = None
            env = service_config.get("environment", {})
            if isinstance(env, dict):
                service_type_override = env.get("SERVICE_TYPE") or env.get("service_type")
            elif isinstance(env, list):
                for env_var in env:
                    if isinstance(env_var, str) and env_var.startswith("SERVICE_TYPE="):
                        service_type_override = env_var.split("=", 1)[1]
                        break

            for port_spec in service_config.get("ports", []) or []:
                parsed = _parse_port_spec(port_spec, service_name=service_name)
                if not parsed:
                    continue
                if service_type_override:
                    parsed["service_type"] = str(service_type_override).lower()
                ports.append(parsed)
    except Exception as e:
        logger.warning(f"Failed to extract ports from {compose_path}: {e}")

    return ports


def extract_port_from_compose(compose_path: Path) -> int:
    """Extract service port from docker-compose.yml."""
    ports = extract_ports_from_compose(compose_path)
    return int(ports[0]["host_port"]) if ports else 8080


def detect_service_type_from_compose(compose_path: Path) -> str:
    """Detect service type (http/tcp) from docker-compose.yml."""
    ports = extract_ports_from_compose(compose_path)
    return str(ports[0]["service_type"]) if ports else "http"
