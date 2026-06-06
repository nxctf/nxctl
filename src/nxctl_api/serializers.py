"""Serialization helpers for API responses."""

from datetime import datetime
from pathlib import Path

from nxctl.core.challenge_config import read_config_key


def serialize_datetime(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def compute_remaining_seconds(value):
    """Return remaining seconds until expiry as int, or None if unknown."""
    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            try:
                value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    if isinstance(value, datetime):
        try:
            return max(0, int((value - datetime.now()).total_seconds()))
        except Exception:
            return None

    return None


def build_extend_availability(runtime_service, config, challenge_name: str, runtime):
    """Build extend availability state for frontend/API clients."""
    ttl = effective_ttl(runtime_service, config, challenge_name)
    threshold_seconds = int((ttl["extend_threshold_minutes"] or 0) * 60)
    check_extend_cooldown = getattr(runtime_service, "check_extend_cooldown", None)
    if callable(check_extend_cooldown):
        cooldown_remaining = check_extend_cooldown(challenge_name) or 0
    else:
        cooldown_remaining = 0

    remaining_seconds = compute_remaining_seconds(getattr(runtime, "expires_at", None))
    eligible_in_seconds = None
    window_open = False

    if remaining_seconds is not None:
        eligible_in_seconds = max(0, remaining_seconds - threshold_seconds)
        window_open = remaining_seconds <= threshold_seconds

    can_extend = bool(
        getattr(runtime, "status", None) == "running"
        and remaining_seconds is not None
        and window_open
        and cooldown_remaining == 0
    )

    return {
        "can_extend": can_extend,
        "eligible_in_seconds": eligible_in_seconds,
        "cooldown_remaining_seconds": cooldown_remaining,
        "threshold_seconds": threshold_seconds,
        "extend_minutes": ttl["extend_minutes"],
        "cooldown_seconds": ttl["extend_cooldown_seconds"],
    }


def effective_ttl(runtime_service, config, challenge_name: str) -> dict[str, int]:
    getter = getattr(runtime_service, "effective_ttl", None)
    if callable(getter):
        try:
            return getter(challenge_name)
        except Exception:
            pass
    return {
        "default_minutes": int(getattr(config, "default_ttl_minutes", 15) or 15),
        "extend_minutes": int(getattr(config, "extend_time_minutes", 10) or 10),
        "extend_threshold_minutes": int(getattr(config, "extend_threshold_minutes", 5) or 5),
        "extend_cooldown_seconds": int(getattr(config, "extend_cooldown_seconds", 30) or 30),
    }


def build_restart_availability(runtime_service, challenge_name: str, challenge):
    cooldown = 0
    checker = getattr(runtime_service, "check_restart_cooldown", None)
    if callable(checker):
        cooldown = int(checker(challenge_name) or 0)

    lifecycle = effective_lifecycle(runtime_service, None, challenge_name, challenge)
    enabled = bool(lifecycle["can_restart"])
    return {
        "can_restart": enabled and cooldown == 0,
        "enabled": enabled,
        "cooldown_remaining_seconds": cooldown,
        "cooldown_seconds": int(lifecycle["restart_cooldown_seconds"]),
    }


def effective_lifecycle(runtime_service, config, challenge_name: str, challenge) -> dict[str, int | bool]:
    getter = getattr(runtime_service, "effective_lifecycle", None)
    if callable(getter):
        try:
            return getter(challenge_name)
        except Exception:
            pass

    can_restart = getattr(challenge, "can_restart", None)
    if can_restart is None:
        can_restart = bool(getattr(config, "can_restart", True)) if config is not None else True

    cooldown = getattr(challenge, "restart_cooldown_seconds", None)
    if cooldown is None:
        cooldown = int(getattr(config, "restart_cooldown_seconds", 300) or 0) if config is not None else 300

    return {
        "can_restart": bool(can_restart),
        "restart_cooldown_seconds": int(cooldown),
    }


def get_extend_cooldown(runtime_service, challenge_name: str) -> int:
    checker = getattr(runtime_service, "check_extend_cooldown", None)
    if not callable(checker):
        return 0
    return int(checker(challenge_name) or 0)


def safe_exports(export_manager, name: str, health: bool = False):
    """List exports without crashing the endpoint on provider issues."""
    try:
        exports = export_manager.list_exports(name, check_health=health)
        results = []
        for export in exports:
            results.append({
                "type": export.get("type"),
                "provider": export.get("provider"),
                "url": export.get("url") or export.get("endpoint"),
                "endpoint": export.get("url") or export.get("endpoint"),
                "port": export.get("port"),
                "status": export.get("status"),
                "pid": export.get("pid"),
            })
        return results
    except Exception as exc:
        return [{
            "type": "unknown",
            "provider": "unknown",
            "url": None,
            "endpoint": None,
            "port": None,
            "status": "error",
            "pid": None,
            "error": str(exc),
        }]


def serialize_ports(ports):
    return [
        {
            "host_port": port.host_port,
            "internal_port": port.internal_port,
            "type": port.service_type,
            "protocol": port.protocol,
            "service_name": port.service_name,
            "primary": port.is_primary,
        }
        for port in ports
    ]


def serialize_challenge_basic(challenge, runtime_service=None, config=None):
    lifecycle = effective_lifecycle(runtime_service, config, challenge.name, challenge)
    return {
        "name": challenge.name,
        "type": challenge.service_type,
        "port": challenge.service_port or None,
        "path": challenge.path,
        "enabled": challenge.enabled,
        "requires_key": bool(getattr(challenge, "access_key_hash", "")),
        "can_restart": bool(lifecycle["can_restart"]),
        "restart_cooldown_seconds": int(lifecycle["restart_cooldown_seconds"]),
    }


def read_challenge_access_key(config, challenge):
    if not bool(getattr(challenge, "access_key_hash", "")):
        return None

    key_source = str(getattr(challenge, "access_key_source", "") or "").strip()
    chall_dir = getattr(config, "chall_dir", None) if config is not None else None
    if not key_source or chall_dir is None:
        return None

    try:
        chall_root = Path(chall_dir).resolve()
        key_path = (chall_root / key_source).resolve()
        key_path.relative_to(chall_root)
        key = read_config_key(key_path)
    except Exception:
        return None

    return key or None


def serialize_challenge_admin(challenge, config):
    key = read_challenge_access_key(config, challenge)
    requires_key = bool(getattr(challenge, "access_key_hash", ""))
    return {
        "name": challenge.name,
        "key": key,
        "requires_key": requires_key,
        "key_available": key is not None,
        "key_source": str(getattr(challenge, "access_key_source", "") or ""),
        "enabled": challenge.enabled,
    }


def serialize_challenge_with_runtime(challenge, runtime, runtime_service=None, config=None):
    status_value = getattr(runtime, "status", "unknown") or "unknown"
    return serialize_challenge_basic(challenge, runtime_service, config) | {
        "status": status_value,
        "running": status_value == "running",
        "remaining_seconds": compute_remaining_seconds(
            getattr(runtime, "expires_at", None)
        ),
    }
