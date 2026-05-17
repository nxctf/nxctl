"""Challenge lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException

from nxctl_api.auth import verify_admin_secret, verify_client_token
from nxctl_api.serializers import (
    build_extend_availability,
    compute_remaining_seconds,
)
from nxctl_api.services import start_challenge_payload
from nxctl.scripts.cli.base import get_services
from nxctl.scripts.cli.lifecycle import (
    _start_available_exports,
    _stop_challenge_completely,
)

router = APIRouter()


@router.post("/up/{name}", dependencies=[Depends(verify_client_token)])
async def up_challenge(name: str):
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        return start_challenge_payload(
            name,
            challenge_service,
            runtime_service,
            export_manager,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/up", dependencies=[Depends(verify_admin_secret)])
async def up_all_challenges(all: bool = False):
    if not all:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "missing_all_flag",
            },
        )

    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        results = []
        failures = []

        for challenge in challenge_service.list_challenges():
            if not challenge.enabled:
                continue
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

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": "up_all_failed",
                "message": str(exc),
            },
        )


@router.post("/down/{name}", dependencies=[Depends(verify_admin_secret)])
async def down_challenge(name: str):
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
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
async def down_all_challenges(all: bool = False):
    if not all:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "missing_all_flag",
            },
        )

    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        handled = []
        failures = []

        for challenge in challenge_service.list_challenges():
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


@router.post("/restart/{name}", dependencies=[Depends(verify_client_token)])
async def restart_challenge(
    name: str,
    container: bool = False,
    provider: bool = False,
):
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        remaining = runtime_service.check_restart_cooldown(name)

        if remaining:
            raise HTTPException(
                status_code=429,
                detail=f"Restart cooldown active. Wait {remaining}s",
            )

        restart_all = not (container or provider)
        do_container = restart_all or container
        do_provider = restart_all or provider

        challenge = challenge_service.get_challenge(name)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        if do_provider:
            export_manager.stop_all_exports(name)

        if do_container:
            runtime_service.stop(name)
            runtime_service.start(name)
            challenge = challenge_service.get_challenge(name)

        if do_provider:
            ports = challenge_service.list_challenge_ports(name)
            exports, failures = _start_available_exports(
                export_manager,
                name,
                challenge,
                ports,
            )
        else:
            exports, failures = [], []

        runtime_service.update_restart_time(name)

        return {
            "message": f"Challenge {name} restarted",
            "scope": "all" if restart_all else "container" if container else "provider",
            "exports": exports,
            "export_failures": failures,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/extend/{name}", dependencies=[Depends(verify_client_token)])
async def extend_challenge(name: str):
    try:
        config, _, runtime_service, _ = get_services()
        runtime = runtime_service.status(name)
        extend_availability = build_extend_availability(
            runtime_service,
            config,
            name,
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
            name,
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
