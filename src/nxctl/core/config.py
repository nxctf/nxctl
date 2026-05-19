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
    """Main application configuration.

    User-facing config should set only data_dir for NXCTL-owned filesystem
    state. All internal runtime paths are derived from that root.
    """

    github_repo: str
    branch: str = "main"
    access_token: str = ""

    data_dir: str = "./data"
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

    # TTL settings
    default_ttl_minutes: int = 15
    extend_time_minutes: int = 10
    extend_threshold_minutes: int = 5
    extend_cooldown_seconds: int = 30
    daemon_interval: int = 10
    restart_cooldown_seconds: int = 300
    auto_heal_exports: bool = True
    export_endpoint_check_interval_seconds: int = 120
    export_endpoint_check_timeout_seconds: int = 5

    class Config:
        extra = "allow"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def chall_dir(self) -> Path:
        return self.data_path / "chall"

    @property
    def db_file(self) -> Path:
        return self.data_path / "nxctl.db"

    @property
    def runtime_dir(self) -> Path:
        return self.data_path / "runtime"

    @property
    def state_dir(self) -> Path:
        return self.runtime_dir / "state"

    @property
    def locks_dir(self) -> Path:
        return self.runtime_dir / "locks"

    @property
    def tmp_dir(self) -> Path:
        return self.runtime_dir / "tmp"

    @property
    def compose_dir(self) -> Path:
        return self.runtime_dir / "compose"

    @property
    def logs_dir(self) -> Path:
        return self.data_path / "logs"

    @property
    def export_logs_dir(self) -> Path:
        return self.logs_dir / "exports"

    @property
    def legacy_exports_dir(self) -> Path:
        return self.data_path / "exports"

    @property
    def cache_dir(self) -> Path:
        """Legacy alias. New code should use chall_dir or data_dir."""
        return self.data_path

    @property
    def dir_app(self) -> Path:
        """Legacy alias for data_dir."""
        return self.data_path

    @property
    def exports_dir(self) -> Path:
        """Legacy alias for the old export artifact directory."""
        return self.legacy_exports_dir

    @property
    def export_state_dir(self) -> Path:
        """Legacy alias for the active export state directory."""
        return self.state_dir

    @property
    def runtime_compose_dir(self) -> Path:
        """Legacy alias for compose_dir."""
        return self.compose_dir

    def path(self, name: str) -> Path:
        """Return a configured filesystem path as a Path object."""
        if not hasattr(self, name):
            raise AttributeError(f"Unknown config path: {name}")
        value = getattr(self, name)
        return value if isinstance(value, Path) else Path(value)

    def ensure_dirs(self) -> None:
        """Create the runtime directories NXCTL owns."""
        for path in (
            self.data_path,
            self.chall_dir,
            self.runtime_dir,
            self.compose_dir,
            self.state_dir,
            self.locks_dir,
            self.tmp_dir,
            self.logs_dir,
            self.export_logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def legacy_export_state_dirs(self) -> list[Path]:
        """State locations from previous layouts, ordered newest to oldest."""
        return [
            self.runtime_dir / "exports" / "state",
            self.legacy_exports_dir,
        ]

    @root_validator(pre=True)
    def _normalize_values(cls, values):
        base_dir = Path(values.get("_config_dir") or os.getcwd()).resolve()

        data_dir = (
            values.get("data_dir")
            or values.get("dir_app")
            or values.get("app_dir")
            or cls._data_dir_from_legacy(values)
            or "./data"
        )
        values["data_dir"] = cls._normalize_path(data_dir, base_dir)

        # Keep accepting old keys, but do not let them create divergent write
        # targets. All active paths are derived from data_dir properties.
        for legacy_key in (
            "dir_app",
            "cache_dir",
            "app_dir",
            "chall_dir",
            "build_dir",
            "db_file",
            "exports_dir",
            "runtime_dir",
            "logs_dir",
            "export_state_dir",
            "export_logs_dir",
            "locks_dir",
            "tmp_dir",
            "runtime_compose_dir",
            "data_exports",
            "export_dir",
            "exports_path",
        ):
            values.pop(legacy_key, None)

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

    @classmethod
    def _data_dir_from_legacy(cls, values: dict[str, Any]) -> Any:
        cache_dir = values.get("cache_dir")
        if cache_dir:
            normalized = str(cache_dir).replace("\\", "/").rstrip("/")
            if normalized.endswith("/chall") or normalized.endswith("/cache"):
                return str(Path(cache_dir).parent)
            return cache_dir

        for key, marker in (
            ("chall_dir", "chall"),
            ("db_file", "nxctl.db"),
            ("exports_dir", "exports"),
            ("runtime_dir", "runtime"),
            ("logs_dir", "logs"),
        ):
            value = values.get(key)
            if not value:
                continue
            path = Path(str(value))
            if path.name == marker:
                return str(path.parent)

        for key, marker in (
            ("export_state_dir", "state"),
            ("export_logs_dir", "exports"),
            ("locks_dir", "locks"),
            ("tmp_dir", "tmp"),
            ("runtime_compose_dir", "compose"),
        ):
            value = values.get(key)
            if not value:
                continue
            path = Path(str(value))
            if path.name != marker:
                continue
            parent = path.parent
            if parent.name == "runtime":
                return str(parent.parent)
            if parent.name == "logs":
                return str(parent.parent)

        return None

    @staticmethod
    def _normalize_path(value: Any, base_dir: Path | None = None) -> str:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = (base_dir or Path.cwd()).resolve() / path
        normalized = str(path.resolve()).replace("\\", "/")
        if re.fullmatch(r"[A-Za-z]:/", normalized) or normalized == "/":
            return normalized
        return normalized.rstrip("/")


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR_NAME} with environment variables."""
    if isinstance(value, str):
        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        return re.sub(r"\$\{([A-Z0-9_]+)\}", replace_env, value)
    if isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    return value


def load_config(config_path: str = "config.yml") -> Config:
    """Load configuration from YAML file."""
    config_file = Path(config_path).expanduser()
    if not config_file.is_absolute():
        config_file = (Path.cwd() / config_file).resolve()
    else:
        config_file = config_file.resolve()

    env_file = config_file.parent / ".env"
    if not env_file.exists():
        env_file = Path(".env")

    if env_file.exists():
        try:
            if load_dotenv:
                load_dotenv(dotenv_path=str(env_file))
            else:
                with open(env_file, "r", encoding="utf-8") as ef:
                    for line in ef:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    config_dict = substitute_env_vars(raw_config)
    config_dict["_config_dir"] = str(config_file.parent)

    config = Config(**config_dict)
    config.ensure_dirs()
    return config


def get_config(config_path: str = "config.yml") -> Config:
    """Get configuration instance (singleton pattern)."""
    if not hasattr(get_config, "_instance"):
        get_config._instance = load_config(config_path)
    return get_config._instance
