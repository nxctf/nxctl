"""FastAPI implementation for NXCTL."""

import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import APIKeyHeader

from nxctl.scripts.cli.base import get_services
from nxctl.scripts.cli.lifecycle import (
    _stop_challenge_completely,
    _start_with_fallback
)

app = FastAPI(
    title="NXCTL API",
    description="API for NXCTL challenge orchestration"
)

# =========================================================
# Security
# =========================================================

API_KEY_NAME = "X-NXCTL-Token"

api_key_header = APIKeyHeader(
    name=API_KEY_NAME,
    auto_error=False
)


def get_api_token():
    return (
        os.getenv("NXCTL_API_TOKEN")
        or "default_secret_token_change_me"
    )


async def verify_token(api_key: str = Depends(api_key_header)):
    expected_token = get_api_token()

    if not api_key or api_key != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Token"
        )

    return api_key


# =========================================================
# Helpers
# =========================================================

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

    # If it's a string, try to parse common datetime formats
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            try:
                value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    if isinstance(value, datetime):
        now = datetime.now()
        try:
            secs = int((value - now).total_seconds())
            return max(0, secs)
        except Exception:
            return None

    return None


def build_extend_availability(runtime_service, config, challenge_name: str, runtime):
    """
    Build extend availability state for frontend.

    Returns:
      - can_extend: bool
      - eligible_in_seconds: seconds until challenge enters extend window
      - cooldown_remaining_seconds: seconds until cooldown clears
      - threshold_seconds: extend threshold in seconds
    """
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
    """Compatibility wrapper when RuntimeService has not been reloaded yet."""
    checker = getattr(runtime_service, "check_extend_cooldown", None)
    if not callable(checker):
        return 0
    return int(checker(challenge_name) or 0)


def safe_exports(export_manager, name: str, health: bool = False):
    """
    Safe wrapper for export listing.
    Never crash endpoint because of provider issues.
    """

    try:
        exports = export_manager.list_exports(
            name,
            check_health=health
        )

        results = []

        for e in exports:
            results.append({
                "provider": e.get("provider"),
                "endpoint": e.get("endpoint"),
                "status": e.get("status"),
                "pid": e.get("pid")
            })

        return results

    except Exception as e:
        return [{
            "provider": "unknown",
            "endpoint": None,
            "status": "error",
            "pid": None,
            "error": str(e)
        }]


# =========================================================
# Root
# =========================================================

@app.get("/")
async def root():
    return {
        "message": "NXCTL API is running",
        "status": "ok"
    }


# =========================================================
# Challenges
# =========================================================

@app.get(
    "/challenges",
    dependencies=[Depends(verify_token)]
)
async def list_challenges():
    _, challenge_service, _, _ = get_services()

    challenges = challenge_service.list_challenges()

    return [
        {
            "name": c.name,
            "type": c.service_type,
            "port": c.service_port,
            "path": c.path,
            "enabled": c.enabled
        }
        for c in challenges
    ]


# =========================================================
# Status
# =========================================================

@app.get(
    "/status",
    dependencies=[Depends(verify_token)]
)
async def get_all_status():
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager
        ) = get_services()

        challenges = challenge_service.list_challenges()

        results = []

        for c in challenges:
            runtime = runtime_service.status(c.name)

            cooldown = (
                runtime_service.check_restart_cooldown(c.name)
                or 0
            )

            extend_cooldown = get_extend_cooldown(
                runtime_service,
                c.name
            )

            extend_availability = build_extend_availability(
                runtime_service,
                config,
                c.name,
                runtime
            )

            results.append({
                "name": c.name,
                "status": runtime.status,
                "container_id": runtime.container_id,
                "remaining_seconds": compute_remaining_seconds(
                    runtime.expires_at
                ),
                "restart_cooldown": cooldown,
                "extend_cooldown": extend_cooldown,
                "extend": extend_availability,
                "exports": safe_exports(
                    export_manager,
                    c.name,
                    health=False
                )
            })

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# Inspect
# =========================================================

@app.get(
    "/inspect/{name}",
    dependencies=[Depends(verify_token)]
)
async def inspect_challenge(name: str):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager
        ) = get_services()

        challenge = challenge_service.get_challenge(name)

        if not challenge:
            raise HTTPException(
                status_code=404,
                detail="Challenge not found"
            )

        runtime = runtime_service.status(name)
        extend_availability = build_extend_availability(
            runtime_service,
            config,
            name,
            runtime
        )

        return {
            "challenge": {
                "name": challenge.name,
                "path": challenge.path,
                "port": challenge.service_port,
                "type": challenge.service_type,
                "enabled": challenge.enabled,
                "created_at": serialize_datetime(
                    challenge.created_at
                )
            },

            "runtime": {
                "status": runtime.status,
                "container_id": runtime.container_id,
                "remaining_seconds": compute_remaining_seconds(
                    runtime.expires_at
                ),
                "restart_cooldown":
                    runtime_service.check_restart_cooldown(name)
                    or 0,
                "extend_cooldown":
                    get_extend_cooldown(runtime_service, name),
                "extend": extend_availability
            },

            "exports": safe_exports(
                export_manager,
                name,
                health=True
            )
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# UP
# =========================================================

@app.post(
    "/up/{name}",
    dependencies=[Depends(verify_token)]
)
async def up_challenge(name: str):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager
        ) = get_services()

        challenge = challenge_service.get_challenge(name)

        if not challenge:
            raise HTTPException(
                status_code=404,
                detail="Challenge not found"
            )

        runtime_service.start(name)

        challenge = challenge_service.get_challenge(name)

        provider, endpoint = _start_with_fallback(
            export_manager,
            name,
            challenge
        )

        return {
            "message": f"Challenge {name} is up",
            "provider": provider,
            "endpoint": endpoint
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# DOWN
# =========================================================

@app.post(
    "/down/{name}",
    dependencies=[Depends(verify_token)]
)
async def down_challenge(name: str):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager
        ) = get_services()

        _stop_challenge_completely(
            name,
            challenge_service,
            runtime_service,
            export_manager
        )

        return {
            "message": f"Challenge {name} stopped"
        }

    except Exception as e:
        import traceback

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# Restart
# =========================================================

@app.post(
    "/restart/{name}",
    dependencies=[Depends(verify_token)]
)
async def restart_challenge(
    name: str,
    container: bool = False,
    provider: bool = False
):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager
        ) = get_services()

        remaining = runtime_service.check_restart_cooldown(name)

        if remaining:
            raise HTTPException(
                status_code=429,
                detail=f"Restart cooldown active. Wait {remaining}s"
            )

        restart_all = not (container or provider)

        do_container = restart_all or container
        do_provider = restart_all or provider

        challenge = challenge_service.get_challenge(name)

        if not challenge:
            raise HTTPException(
                status_code=404,
                detail="Challenge not found"
            )

        # Stop provider
        if do_provider:
            exports = export_manager.list_exports(name)

            for export in exports:
                export_manager.stop_export(
                    name,
                    export["provider"],
                    challenge.service_port
                )

        # Restart container
        if do_container:
            runtime_service.stop(name)
            runtime_service.start(name)

            challenge = challenge_service.get_challenge(name)

        # Start provider
        if do_provider:
            _start_with_fallback(
                export_manager,
                name,
                challenge
            )

        runtime_service.update_restart_time(name)

        return {
            "message": f"Challenge {name} restarted",
            "scope":
                "all"
                if restart_all
                else (
                    "container"
                    if container
                    else "provider"
                )
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# Extend
# =========================================================

@app.post(
    "/extend/{name}",
    dependencies=[Depends(verify_token)]
)
async def extend_challenge(name: str):
    try:
        config, _, runtime_service, _ = get_services()
        runtime = runtime_service.status(name)

        extend_availability = build_extend_availability(
            runtime_service,
            config,
            name,
            runtime
        )

        cooldown = extend_availability["cooldown_remaining_seconds"]
        if cooldown:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": "Extend cooldown active",
                    "remaining_seconds": cooldown,
                    "extend": extend_availability
                }
            )

        if not extend_availability["can_extend"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Extend not yet eligible",
                    "extend": extend_availability
                }
            )

        runtime = runtime_service.extend_time(name)
        extend_after = build_extend_availability(
            runtime_service,
            config,
            name,
            runtime
        )

        return {
            "message": f"Challenge {name} extended",
            "remaining_seconds": compute_remaining_seconds(
                runtime.expires_at
            ),
            "extend": extend_after
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
