"""Configuration management for NXCTL."""

import os
import re
from pathlib import Path
from typing import Any

import yaml

# Optional .env support
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from pydantic import BaseModel, Field, root_validator


class Config(BaseModel):
    """Main application configuration."""
    github_repo: str
    branch: str = "main"
    access_token: str = ""

    dir_app: str = "./data"
    cache_dir: str = "./data"
    build_dir: str = "./data/build"
    db_file: str = "./data/nxctl.db"
    exports_dir: str = "./data/exports"
    export_logs_dir: str = "./data/exports/logs"
    export_active_logs_dir: str = "./data/exports/logs/active"
    export_archive_logs_dir: str = "./data/exports/logs/archive"
    base_ip: str = ""
    api_token: str = ""
    api_admin_secret: str = ""

    ngrok_tokens: list[str] = Field(default_factory=list)
    pinggy_token: str = ""

    default_tunnel: str = "localtunnel"
    enable_ngrok: bool = True
    enable_localtunnel: bool = True
    enable_pinggy: bool = True
    local_port_start: int = 40000
    local_port_end: int = 49999
    randomize_local_ports: bool = True
    docker_start_port_retries: int = 5

    # TTL settings
    default_ttl_minutes: int = 15
    extend_time_minutes: int = 10
    extend_threshold_minutes: int = 5
    extend_cooldown_seconds: int = 30
    daemon_interval: int = 10
    restart_cooldown_seconds: int = 300
    auto_heal_exports: bool = True
    export_auto_heal_interval_seconds: int = 120
    export_start_lock_timeout_seconds: int = 60
    export_start_lock_stale_seconds: int = 180
    export_endpoint_check_interval_seconds: int = 120
    export_endpoint_check_timeout_seconds: int = 5
    export_endpoint_check_grace_seconds: int = 120
    pinggy_startup_retries: int = 3
    pinggy_start_timeout_seconds: int = 30
    pinggy_ready_probe_timeout_seconds: int = 2
    pinggy_stability_seconds: int = 10
    pinggy_start_probe_connect: bool = False
    localtunnel_stability_seconds: int = 5

    class Config:
        extra = "allow"

    @root_validator(pre=True)
    def _normalize_values(cls, values):
        dir_app = values.get("dir_app") or values.get("data_dir") or values.get("app_dir")
        cache_dir = values.get("cache_dir")

        if not dir_app and cache_dir:
            normalized_cache = cls._normalize_path(cache_dir)
            if normalized_cache.endswith("/chall") or normalized_cache.endswith("/cache"):
                dir_app = str(Path(normalized_cache).parent).replace("\\", "/")
            else:
                dir_app = normalized_cache

        dir_app = cls._normalize_path(dir_app or "./data")
        values["dir_app"] = dir_app

        # Internally cache_dir means the NXCTL data root. Keep accepting legacy
        # cache_dir values like ./data/chall, but normalize them to ./data.
        values["cache_dir"] = dir_app

        if not values.get("build_dir"):
            values["build_dir"] = str(Path(dir_app) / "build").replace("\\", "/")

        if not values.get("db_file"):
            values["db_file"] = str(Path(dir_app) / "nxctl.db").replace("\\", "/")

        exports_dir = (
            values.get("exports_dir")
            or values.get("data_exports")
            or values.get("export_dir")
            or values.get("exports_path")
        )
        values["exports_dir"] = cls._normalize_path(exports_dir or str(Path(dir_app) / "exports"))
        values["export_logs_dir"] = cls._normalize_path(
            values.get("export_logs_dir") or str(Path(values["exports_dir"]) / "logs")
        )
        values["export_active_logs_dir"] = cls._normalize_path(
            values.get("export_active_logs_dir") or str(Path(values["export_logs_dir"]) / "active")
        )
        values["export_archive_logs_dir"] = cls._normalize_path(
            values.get("export_archive_logs_dir") or str(Path(values["export_logs_dir"]) / "archive")
        )

        if not values.get("ngrok_tokens"):
            legacy_tunnels = values.get("tunnels", {}) or {}
            legacy_ngrok = legacy_tunnels.get("ngrok", {}) if isinstance(legacy_tunnels, dict) else {}
            legacy_tokens = legacy_ngrok.get("tokens", []) if isinstance(legacy_ngrok, dict) else []
            tokens: list[str] = []
            for token_item in legacy_tokens:
                if isinstance(token_item, str) and token_item.strip():
                    tokens.append(token_item.strip())
                elif isinstance(token_item, dict):
                    token_value = str(token_item.get("token", "")).strip()
                    if token_value:
                        tokens.append(token_value)
            if tokens:
                values["ngrok_tokens"] = tokens

        if not values.get("pinggy_token"):
            legacy_tunnels = values.get("tunnels", {}) or {}
            legacy_pinggy = legacy_tunnels.get("pinggy", {}) if isinstance(legacy_tunnels, dict) else {}
            if isinstance(legacy_pinggy, dict):
                legacy_token = str(legacy_pinggy.get("token", "")).strip()
                if legacy_token:
                    values["pinggy_token"] = legacy_token

        return values

    @staticmethod
    def _normalize_path(value: Any) -> str:
        return str(value).replace("\\", "/").rstrip("/") or "."


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR_NAME} with environment variables."""
    if isinstance(value, str):
        # Replace ${VAR_NAME} with environment variable values
        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        return re.sub(r'\$\{([A-Z0-9_]+)\}', replace_env, value)
    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    return value


def load_config(config_path: str = "config.yml") -> Config:
    """Load configuration from YAML file."""
    config_file = Path(config_path)

    # Auto-load .env into environment if present
    # Look for .env in the config directory or repo root
    env_file = config_file.parent / ".env"
    if not env_file.exists():
        env_file = Path(".env")

    if env_file.exists():
        try:
            if load_dotenv:
                load_dotenv(dotenv_path=str(env_file))
            else:
                # Minimal manual loader: parse KEY=VALUE lines
                with open(env_file, "r") as ef:
                    for line in ef:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            os.environ.setdefault(k, v)
        except Exception:
            # If dotenv loading fails, continue without failing
            pass

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r") as f:
        raw_config = yaml.safe_load(f) or {}

    # Substitute environment variables
    config_dict = substitute_env_vars(raw_config)

    # Parse and validate
    config = Config(**config_dict)

    return config


def get_config(config_path: str = "config.yml") -> Config:
    """Get configuration instance (singleton pattern)."""
    if not hasattr(get_config, "_instance"):
        get_config._instance = load_config(config_path)
    return get_config._instance
