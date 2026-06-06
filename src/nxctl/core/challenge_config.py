"""Challenge-local nxctl.yml metadata loading."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


CHALLENGE_CONFIG_FILENAME = "nxctl.yml"
TTL_FIELDS = (
    "default_minutes",
    "extend_minutes",
    "extend_threshold_minutes",
    "extend_cooldown_seconds",
)


class ChallengeConfigError(Exception):
    """Raised when challenge-local metadata is invalid."""


@dataclass
class ChallengeLocalConfig:
    """Effective challenge-local metadata after inheritance."""

    key: str = ""
    key_source: str = ""
    enabled: bool | None = None
    ttl: dict[str, int] = field(default_factory=dict)
    can_restart: bool | None = None
    restart_cooldown_seconds: int | None = None
    config_sources: list[str] = field(default_factory=list)


def load_inherited_challenge_config(challenge_dir: Path, repo_root: Path) -> ChallengeLocalConfig:
    """Load inherited nxctl.yml files from repo root to challenge dir."""
    try:
        current = challenge_dir.resolve()
        root = repo_root.resolve()
        current.relative_to(root)
    except Exception:
        return ChallengeLocalConfig()

    directories = []
    directory = current
    while True:
        directories.append(directory)
        if directory == root or directory.parent == directory:
            break
        directory = directory.parent
    directories.reverse()

    effective = ChallengeLocalConfig()
    for directory in directories:
        config_path = directory / CHALLENGE_CONFIG_FILENAME
        if not config_path.is_file():
            continue

        raw_config = read_challenge_config_file(config_path)
        source = relative_repo_path(config_path, root)
        effective.config_sources.append(source)

        if "key" in raw_config:
            key = normalize_key(raw_config.get("key"))
            if key:
                effective.key = key
                effective.key_source = source

        enabled_field = "enabled" if "enabled" in raw_config else "enable" if "enable" in raw_config else ""
        if enabled_field:
            effective.enabled = parse_bool(
                raw_config[enabled_field],
                source,
                enabled_field,
            )

        ttl_config = raw_config.get("ttl")
        if ttl_config is not None:
            if not isinstance(ttl_config, dict):
                raise ChallengeConfigError(f"{source}: `ttl` must be a mapping")
            for field_name in TTL_FIELDS:
                if field_name in ttl_config:
                    value = parse_non_negative_int(ttl_config[field_name], source, f"ttl.{field_name}")
                    if value is not None:
                        effective.ttl[field_name] = value

        lifecycle_config = raw_config.get("lifecycle")
        if lifecycle_config is None and "chall" in raw_config:
            lifecycle_config = raw_config.get("chall")
        if lifecycle_config is not None:
            if not isinstance(lifecycle_config, dict):
                raise ChallengeConfigError(f"{source}: `lifecycle` must be a mapping")
            if "can_restart" in lifecycle_config:
                effective.can_restart = parse_bool(
                    lifecycle_config["can_restart"],
                    source,
                    "lifecycle.can_restart",
                )
            if "restart_cooldown_seconds" in lifecycle_config:
                effective.restart_cooldown_seconds = parse_non_negative_int(
                    lifecycle_config["restart_cooldown_seconds"],
                    source,
                    "lifecycle.restart_cooldown_seconds",
                )

    return effective


def read_challenge_config_file(config_path: Path) -> dict[str, Any]:
    """Read one nxctl.yml file as a mapping."""
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except UnicodeDecodeError:
        raw_config = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ChallengeConfigError(f"{config_path}: invalid YAML: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ChallengeConfigError(f"{config_path}: top-level config must be a mapping")
    return raw_config


def read_config_key(config_path: Path) -> str:
    """Read the raw access key from one nxctl.yml file."""
    raw_config = read_challenge_config_file(config_path)
    return normalize_key(raw_config.get("key"))


def normalize_key(value: Any) -> str:
    return str(value or "").strip()


def parse_non_negative_int(value: Any, source: str, field_name: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ChallengeConfigError(f"{source}: `{field_name}` must be an integer") from exc
    if parsed < 0:
        raise ChallengeConfigError(f"{source}: `{field_name}` must be non-negative")
    return parsed


def parse_bool(value: Any, source: str, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "on"}:
            return True
        if lowered in {"false", "no", "n", "0", "off"}:
            return False
    raise ChallengeConfigError(f"{source}: `{field_name}` must be true or false")


def relative_repo_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path)
