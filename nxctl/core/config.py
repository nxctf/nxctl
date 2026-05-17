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

    cache_dir: str = "./data/chall"
    build_dir: str = "./data/build"
    db_file: str = "./data/nxctl.db"

    ngrok_tokens: list[str] = Field(default_factory=list)
    pinggy_token: str = ""

    default_tunnel: str = "localtunnel"
    enable_ngrok: bool = True
    enable_localtunnel: bool = True
    enable_pinggy: bool = True

    # TTL settings
    default_ttl_minutes: int = 15
    extend_time_minutes: int = 10
    extend_threshold_minutes: int = 5
    extend_cooldown_seconds: int = 30
    daemon_interval: int = 10
    restart_cooldown_seconds: int = 300
    auto_heal_exports: bool = True

    class Config:
        extra = "allow"

    @root_validator(pre=True)
    def _normalize_values(cls, values):
        cache_dir = values.get("cache_dir")
        if not cache_dir:
            values["cache_dir"] = "./data"
        else:
            normalized = str(cache_dir).replace("\\", "/").rstrip("/")
            if normalized in {"./data/chall", "data/chall", "./data/cache", "data/cache"}:
                values["cache_dir"] = "./data"

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
