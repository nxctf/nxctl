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


class ChallengesConfig(BaseModel):
    github_repo: str = ""
    branch: str = "main"
    access_token: str = ""

    class Config:
        extra = "allow"


class AppConfig(BaseModel):
    data_dir: str = "./data"
    base_ip: str = ""

    class Config:
        extra = "allow"


class ApiConfig(BaseModel):
    token: str = ""
    admin_secret: str = ""

    class Config:
        extra = "allow"


class TtlConfig(BaseModel):
    default_minutes: int = 15
    extend_minutes: int = 10
    extend_threshold_minutes: int = 5
    extend_cooldown_seconds: int = 30

    class Config:
        extra = "allow"


class DaemonConfig(BaseModel):
    interval_seconds: int = 10
    restart_cooldown_seconds: int = 300

    class Config:
        extra = "allow"


class ExportsConfig(BaseModel):
    auto_heal: bool = True
    endpoint_check_interval_seconds: int = 120
    endpoint_check_timeout_seconds: int = 5

    class Config:
        extra = "allow"


class PortsConfig(BaseModel):
    local_start: int = 40000
    local_end: int = 49999
    randomize: bool = True

    class Config:
        extra = "allow"


class NgrokConfig(BaseModel):
    enabled: bool = True
    max_sessions_per_token: int = 3
    tokens: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


class LocalTunnelConfig(BaseModel):
    enabled: bool = True

    class Config:
        extra = "allow"


class PinggyConfig(BaseModel):
    enabled: bool = True
    max_sessions_per_token: int = 1
    tokens: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


class CloudflareConfig(BaseModel):
    enabled: bool = True
    token: str = ""
    tunnel_name: str = ""
    credentials_file: str = ""
    subdomains: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


class BoreConfig(BaseModel):
    enabled: bool = True
    server: str = "bore.pub"

    class Config:
        extra = "allow"


class TunnelsConfig(BaseModel):
    ngrok: NgrokConfig = Field(default_factory=NgrokConfig)
    localtunnel: LocalTunnelConfig = Field(default_factory=LocalTunnelConfig)
    pinggy: PinggyConfig = Field(default_factory=PinggyConfig)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    bore: BoreConfig = Field(default_factory=BoreConfig)

    class Config:
        extra = "allow"


class Config(BaseModel):
    """Main application configuration.

    User-facing config should set only data_dir for NXCTL-owned filesystem
    state. All internal runtime paths are derived from that root.
    """

    challenges: ChallengesConfig = Field(default_factory=ChallengesConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    ttl: TtlConfig = Field(default_factory=TtlConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    exports: ExportsConfig = Field(default_factory=ExportsConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    tunnels: TunnelsConfig = Field(default_factory=TunnelsConfig)

    class Config:
        extra = "allow"

    # =========================================================================
    # Legacy Properties for Backward Compatibility
    # =========================================================================

    @property
    def github_repo(self) -> str:
        return self.challenges.github_repo

    @property
    def branch(self) -> str:
        return self.challenges.branch

    @property
    def access_token(self) -> str:
        return self.challenges.access_token

    @property
    def data_dir(self) -> str:
        return self.app.data_dir

    @property
    def base_ip(self) -> str:
        return self.app.base_ip

    @property
    def api_token(self) -> str:
        return self.api.token

    @property
    def api_admin_secret(self) -> str:
        return self.api.admin_secret

    @property
    def ngrok_tokens(self) -> list[str]:
        return self.tunnels.ngrok.tokens

    @property
    def pinggy_token(self) -> str:
        if self.tunnels.pinggy.tokens:
            return self.tunnels.pinggy.tokens[0]
        return ""

    @property
    def enable_ngrok(self) -> bool:
        return self.tunnels.ngrok.enabled

    @property
    def enable_localtunnel(self) -> bool:
        return self.tunnels.localtunnel.enabled

    @property
    def enable_pinggy(self) -> bool:
        return self.tunnels.pinggy.enabled

    @property
    def enable_cloudflare(self) -> bool:
        return self.tunnels.cloudflare.enabled

    @property
    def cloudflare_tunnel_name(self) -> str:
        return self.tunnels.cloudflare.tunnel_name

    @property
    def cloudflare_credentials_file(self) -> str:
        return self.tunnels.cloudflare.credentials_file

    @property
    def cloudflare_subdomains(self) -> list[str]:
        return self.tunnels.cloudflare.subdomains

    @property
    def enable_bore(self) -> bool:
        return self.tunnels.bore.enabled

    @property
    def bore_server(self) -> str:
        return self.tunnels.bore.server

    @property
    def local_port_start(self) -> int:
        return self.ports.local_start

    @property
    def local_port_end(self) -> int:
        return self.ports.local_end

    @property
    def randomize_local_ports(self) -> bool:
        return self.ports.randomize

    @property
    def default_ttl_minutes(self) -> int:
        return self.ttl.default_minutes

    @property
    def extend_time_minutes(self) -> int:
        return self.ttl.extend_minutes

    @property
    def extend_threshold_minutes(self) -> int:
        return self.ttl.extend_threshold_minutes

    @property
    def extend_cooldown_seconds(self) -> int:
        return self.ttl.extend_cooldown_seconds

    @property
    def daemon_interval(self) -> int:
        return self.daemon.interval_seconds

    @property
    def restart_cooldown_seconds(self) -> int:
        return self.daemon.restart_cooldown_seconds

    @property
    def auto_heal_exports(self) -> bool:
        return self.exports.auto_heal

    @property
    def export_endpoint_check_interval_seconds(self) -> int:
        return self.exports.endpoint_check_interval_seconds

    @property
    def export_endpoint_check_timeout_seconds(self) -> int:
        return self.exports.endpoint_check_timeout_seconds

    # =========================================================================
    # Path Properties
    # =========================================================================

    @property
    def data_path(self) -> Path:
        return Path(self.app.data_dir)

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
        for path_obj in (
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
            path_obj.mkdir(parents=True, exist_ok=True)

    def legacy_export_state_dirs(self) -> list[Path]:
        """State locations from previous layouts, ordered newest to oldest."""
        return [
            self.runtime_dir / "exports" / "state",
            self.legacy_exports_dir,
        ]

    @root_validator(pre=True)
    def _normalize_values(cls, values):
        base_dir = Path(values.get("_config_dir") or os.getcwd()).resolve()

        # Extract legacy data dir values to find the definitive data_dir
        data_dir = (
            values.get("data_dir")
            or values.get("dir_app")
            or values.get("app_dir")
            or cls._data_dir_from_legacy(values)
        )

        # Ensure app config dict exists
        if "app" not in values or not isinstance(values["app"], dict):
            values["app"] = {}

        if data_dir:
            values["app"]["data_dir"] = cls._normalize_path(data_dir, base_dir)
        elif "data_dir" not in values["app"]:
            values["app"]["data_dir"] = cls._normalize_path("./data", base_dir)

        # Map legacy flat keys to nested dictionaries
        legacy_mappings = {
            "github_repo": ("challenges", "github_repo"),
            "branch": ("challenges", "branch"),
            "access_token": ("challenges", "access_token"),
            "base_ip": ("app", "base_ip"),
            "api_token": ("api", "token"),
            "api_admin_secret": ("api", "admin_secret"),
            "default_ttl_minutes": ("ttl", "default_minutes"),
            "extend_time_minutes": ("ttl", "extend_minutes"),
            "extend_threshold_minutes": ("ttl", "extend_threshold_minutes"),
            "extend_cooldown_seconds": ("ttl", "extend_cooldown_seconds"),
            "daemon_interval": ("daemon", "interval_seconds"),
            "restart_cooldown_seconds": ("daemon", "restart_cooldown_seconds"),
            "auto_heal_exports": ("exports", "auto_heal"),
            "export_endpoint_check_interval_seconds": ("exports", "endpoint_check_interval_seconds"),
            "export_endpoint_check_timeout_seconds": ("exports", "endpoint_check_timeout_seconds"),
            "local_port_start": ("ports", "local_start"),
            "local_port_end": ("ports", "local_end"),
            "randomize_local_ports": ("ports", "randomize"),
            "enable_ngrok": ("tunnels", "ngrok", "enabled"),
            "enable_localtunnel": ("tunnels", "localtunnel", "enabled"),
            "enable_pinggy": ("tunnels", "pinggy", "enabled"),
            "enable_cloudflare": ("tunnels", "cloudflare", "enabled"),
            "enable_bore": ("tunnels", "bore", "enabled"),
            "bore_server": ("tunnels", "bore", "server"),
            "ngrok_tokens": ("tunnels", "ngrok", "tokens"),
            "ngrok_max_sessions_per_token": ("tunnels", "ngrok", "max_sessions_per_token"),
        }

        # Handle legacy flat pinggy_token
        if "pinggy_token" in values:
            flat_pinggy_token = str(values.pop("pinggy_token", "")).strip()
            if flat_pinggy_token:
                if "tunnels" not in values:
                    values["tunnels"] = {}
                if "pinggy" not in values["tunnels"]:
                    values["tunnels"]["pinggy"] = {}
                if "tokens" not in values["tunnels"]["pinggy"]:
                    values["tunnels"]["pinggy"]["tokens"] = []
                if flat_pinggy_token not in values["tunnels"]["pinggy"]["tokens"]:
                    values["tunnels"]["pinggy"]["tokens"].append(flat_pinggy_token)

        for old_key, path in legacy_mappings.items():
            if old_key in values:
                # Traverse and set
                current = values
                for part in path[:-1]:
                    if part not in current or not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]

                # Set only if not already explicitly set in nested struct
                last_part = path[-1]
                if last_part not in current:
                    current[last_part] = values[old_key]

                # Remove legacy key to avoid clutter
                values.pop(old_key)

        # Clean up legacy path keys
        for legacy_key in (
            "dir_app", "cache_dir", "app_dir", "chall_dir", "build_dir",
            "db_file", "exports_dir", "runtime_dir", "logs_dir",
            "export_state_dir", "export_logs_dir", "locks_dir", "tmp_dir",
            "runtime_compose_dir", "data_exports", "export_dir", "exports_path",
            "data_dir",
        ):
            values.pop(legacy_key, None)

        # Process nested tunnels to handle old partial layouts (e.g. tokens in dicts)
        legacy_tunnels = values.get("tunnels", {})
        if isinstance(legacy_tunnels, dict):
            # Ngrok tokens normalization
            legacy_ngrok = legacy_tunnels.get("ngrok", {})
            if isinstance(legacy_ngrok, dict):
                legacy_tokens = legacy_ngrok.get("tokens", [])
                tokens = []
                for token_item in legacy_tokens:
                    if isinstance(token_item, str) and token_item.strip():
                        tokens.append(token_item.strip())
                    elif isinstance(token_item, dict):
                        token_value = str(token_item.get("token", "")).strip()
                        if token_value:
                            tokens.append(token_value)
                if tokens:
                    legacy_tunnels["ngrok"]["tokens"] = tokens

            # Pinggy token normalization
            legacy_pinggy = legacy_tunnels.get("pinggy", {})
            if isinstance(legacy_pinggy, dict):
                if "token" in legacy_pinggy:
                    legacy_token = str(legacy_pinggy.pop("token", "")).strip()
                    if legacy_token:
                        if "tokens" not in legacy_pinggy:
                            legacy_pinggy["tokens"] = []
                        if legacy_token not in legacy_pinggy["tokens"]:
                            legacy_pinggy["tokens"].append(legacy_token)

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
