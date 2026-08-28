"""Challenge lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException

from nxctl_api.auth import (
    ApiAccessContext,
    get_api_access_context,
    require_challenge_access,
    verify_admin_secret,
)
from nxctl_api.serializers import (
    build_extend_availability,
    compute_remaining_seconds,
)
from nxctl.core.utils import LifecycleLock
from nxctl_api.services import start_challenge_payload
from nxctl.scripts.cli.base import get_services
from nxctl.scripts.cli.lifecycle import (
    _stop_challenge_completely,
    restart_challenge_lifecycle,
)

router = APIRouter()


@router.post("/up/{name:path}")
def up_challenge(
    name: str,
    no_cache: bool = False,
    access: ApiAccessContext = Depends(get_api_access_context),
):
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        with LifecycleLock(config):
            challenge = require_challenge_access(
                challenge_service.get_challenge(name),
                access,
            )
            return start_challenge_payload(
                challenge.name,
                challenge_service,
                runtime_service,
                export_manager,
                no_cache=no_cache,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/up", dependencies=[Depends(verify_admin_secret)])
def up_all_challenges(all: bool = False, prefix: str | None = None):
    if not all:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "missing_all_flag",
            },
        )

    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        results = []
        failures = []
        challenges = challenge_service.list_challenges_under(prefix)
        if not challenges:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "error": "no_matching_challenges",
                    "prefix": prefix,
                },
            )

        for challenge in challenges:
            with LifecycleLock(config):
                try:
                    results.append(start_challenge_payload(
                        challenge.name,
                        challenge_service,
                        runtime_service,
                        export_manager,
                    ))
                except HTTPException as exc:
                    failures.append({
                        "challenge": challenge.name,
                        "error": exc.detail,
                    })
                except Exception as exc:
                    failures.append({
                        "challenge": challenge.name,
                        "error": str(exc),
                    })

        return {
            "ok": not failures,
            "started": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "invalid_prefix",
                "message": str(exc),
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": "up_all_failed",
                "message": str(exc),
            },
        )


@router.post("/down/{name:path}", dependencies=[Depends(verify_admin_secret)])
def down_challenge(name: str):
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        with LifecycleLock(config):
            _stop_challenge_completely(
                name,
                challenge_service,
                runtime_service,
                export_manager,
            )
        return {
            "ok": True,
            "message": f"Challenge {name} stopped",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/down", dependencies=[Depends(verify_admin_secret)])
def down_all_challenges(all: bool = False):
    if not all:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "missing_all_flag",
            },
        )

    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        with LifecycleLock(config):
            handled = []
            failures = []

            for challenge in challenge_service.list_challenges(include_disabled=True):
                try:
                    runtime = runtime_service.status(challenge.name)
                    exports = export_manager.list_exports(challenge.name, check_health=False)
                    if runtime.status != "running" and not exports:
                        continue
                    _stop_challenge_completely(
                        challenge.name,
                        challenge_service,
                        runtime_service,
                        export_manager,
                    )
                    handled.append(challenge.name)
                except Exception as exc:
                    failures.append({
                        "challenge": challenge.name,
                        "error": str(exc),
                    })

            killed = export_manager.kill_all_tunnel_processes()
            export_manager.mark_all_exports_inactive()

        return {
            "ok": not failures,
            "stopped": len(handled),
            "tunnel_processes_killed": killed,
            "challenges": handled,
            "failures": failures,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": "down_all_failed",
                "message": str(exc),
            },
        )


@router.post("/admin/down", dependencies=[Depends(verify_admin_secret)])
def admin_down_all_challenges():
    return down_all_challenges(all=True)


@router.post("/admin/down/{name:path}", dependencies=[Depends(verify_admin_secret)])
def admin_down_challenge(name: str):
    return down_challenge(name)


@router.post("/restart/{name:path}")
def restart_challenge(
    name: str,
    container: bool = False,
    provider: bool = False,
    access: ApiAccessContext = Depends(get_api_access_context),
):
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        with LifecycleLock(config):
            challenge = require_challenge_access(
                challenge_service.get_challenge(name),
                access,
            )
            try:
                runtime_service.ensure_restart_allowed(name)
            except Exception as exc:
                if "Restart disabled" in str(exc):
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "ok": False,
                            "error": "restart_disabled",
                            "message": str(exc),
                        },
                    )
                raise
            remaining = runtime_service.check_restart_cooldown(name)

            if remaining:
                raise HTTPException(
                    status_code=429,
                    detail=f"Restart cooldown active. Wait {remaining}s",
                )

            result = restart_challenge_lifecycle(
                name,
                challenge_service,
                runtime_service,
                export_manager,
                container=container,
                provider=provider,
            )

        return {
            "message": f"Challenge {name} restarted",
            "scope": result["scope"],
            "force": result["force"],
            "exports": result["exports"],
            "export_failures": result["export_failures"],
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/admin/restart/{name:path}", dependencies=[Depends(verify_admin_secret)])
def admin_restart_challenge(
    name: str,
    container: bool = False,
    provider: bool = False,
    force: bool = True,
):
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        with LifecycleLock(config):
            challenge = challenge_service.get_challenge(name)
            if not challenge:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "ok": False,
                        "error": "challenge_not_found",
                    },
                )

            result = restart_challenge_lifecycle(
                name,
                challenge_service,
                runtime_service,
                export_manager,
                container=container,
                provider=provider,
                force=force,
            )

        return {
            "ok": True,
            "message": f"Challenge {name} restarted",
            "scope": result["scope"],
            "force": result["force"],
            "exports": result["exports"],
            "export_failures": result["export_failures"],
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/extend/{name:path}")
def extend_challenge(
    name: str,
    access: ApiAccessContext = Depends(get_api_access_context),
):
    try:
        config, challenge_service, runtime_service, _ = get_services()
        with LifecycleLock(config):
            challenge = require_challenge_access(
                challenge_service.get_challenge(name),
                access,
            )
            runtime = runtime_service.status(name)
            extend_availability = build_extend_availability(
                runtime_service,
                config,
                challenge.name,
                runtime,
            )

            cooldown = extend_availability["cooldown_remaining_seconds"]
            if cooldown:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "message": "Extend cooldown active",
                        "remaining_seconds": cooldown,
                        "extend": extend_availability,
                    },
                )

            if not extend_availability["can_extend"]:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Extend not yet eligible",
                        "extend": extend_availability,
                    },
                )

            runtime = runtime_service.extend_time(name)
            extend_after = build_extend_availability(
                runtime_service,
                config,
                challenge.name,
                runtime,
            )

        return {
            "message": f"Challenge {name} extended",
            "remaining_seconds": compute_remaining_seconds(runtime.expires_at),
            "extend": extend_after,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
