"""Serialization helpers for API responses."""

from datetime import datetime


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
    threshold_seconds = int((getattr(config, "extend_threshold_minutes", 5) or 0) * 60)
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


def serialize_challenge_basic(challenge):
    return {
        "name": challenge.name,
        "type": challenge.service_type,
        "port": challenge.service_port,
        "path": challenge.path,
        "enabled": challenge.enabled,
    }


def serialize_challenge_with_runtime(challenge, runtime):
    status_value = getattr(runtime, "status", "unknown") or "unknown"
    return serialize_challenge_basic(challenge) | {
        "status": status_value,
        "running": status_value == "running",
        "remaining_seconds": compute_remaining_seconds(
            getattr(runtime, "expires_at", None)
        ),
    }
