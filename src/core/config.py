"""Configuration management for CTF orchestration engine."""

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

# Optional .env support
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from pydantic import BaseModel, Field, root_validator


class FRPServer(BaseModel):
    """FRP server configuration."""
    name: str
    server_addr: str
    server_port: int
    token: str = Field(default="")


class FRPConfig(BaseModel):
    """FRP tunnel provider configuration."""
    enabled: bool = False
    rotation_strategy: str = "round-robin"  # or 'fallback'
    servers: list[FRPServer] = []


class NgrokToken(BaseModel):
    """ngrok account token."""
    name: str
    token: str = Field(default="")
    region: str = "us"


class NgrokConfig(BaseModel):
    """ngrok tunnel provider configuration."""
    enabled: bool = False
    rotation_strategy: str = "round-robin"
    tokens: list[NgrokToken] = []


class RatholeServer(BaseModel):
    """Rathole server configuration."""
    name: str
    server_addr: str
    server_port: int
    token: str = Field(default="")


class RatholeConfig(BaseModel):
    """Rathole tunnel provider configuration."""
    enabled: bool = False
    rotation_strategy: str = "round-robin"
    servers: list[RatholeServer] = []


class TunnelsConfig(BaseModel):
    """All tunnel providers configuration."""
    frp: FRPConfig = FRPConfig()
    ngrok: NgrokConfig = NgrokConfig()
    rathole: RatholeConfig = RatholeConfig()


class Config(BaseModel):
    """Main application configuration."""
    # Repository
    github_repo: str
    branch: str = "main"
    access_token: str = ""

    # Paths
    cache_dir: str = "./data/chall"
    build_dir: str = "./data/build"
    db_file: str = "./data/ctf-orch.db"

    # Runtime behavior
    idle_timeout_minutes: int = 15
    revert_cooldown_minutes: int = 5
    max_runtime_hours: int = 2

    # Default tunnel
    default_tunnel: str = "frp"

    # Tunnel providers
    tunnels: TunnelsConfig = TunnelsConfig()

    class Config:
        extra = "allow"  # Allow extra fields

    @root_validator(pre=True)
    def _normalize_cache_dir(cls, values):
        cache_dir = values.get("cache_dir")
        if not cache_dir:
            values["cache_dir"] = "./data"
            return values

        normalized = str(cache_dir).replace("\\", "/").rstrip("/")
        if normalized in {"./data/chall", "data/chall", "./data/cache", "data/cache"}:
            values["cache_dir"] = "./data"

        return values


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR_NAME} with environment variables."""
    if isinstance(value, str):
        # Replace ${VAR_NAME} with environment variable values
        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

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
