"""Status and inspect routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from nxctl_api.auth import (
    ApiAccessContext,
    filter_authorized_challenges,
    get_api_access_context,
    require_challenge_access,
)
from nxctl_api.serializers import (
    build_extend_availability,
    compute_remaining_seconds,
    get_extend_cooldown,
    safe_exports,
    serialize_datetime,
)
from nxctl.scripts.cli.base import get_services

router = APIRouter()


def _unique_names(names: list[str] | None) -> list[str]:
    seen = set()
    results = []
    for name in names or []:
        value = str(name or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        results.append(value)
    return results


def _status_payload(config, runtime_service, export_manager, challenge):
    runtime = runtime_service.status(challenge.name)
    extend_availability = build_extend_availability(
        runtime_service,
        config,
        challenge.name,
        runtime,
    )

    return {
        "name": challenge.name,
        "status": runtime.status,
        "container_id": runtime.container_id,
        "remaining_seconds": compute_remaining_seconds(runtime.expires_at),
        "restart_cooldown": runtime_service.check_restart_cooldown(challenge.name) or 0,
        "extend_cooldown": get_extend_cooldown(runtime_service, challenge.name),
        "extend": extend_availability,
        "exports": safe_exports(export_manager, challenge.name, health=False),
    }


@router.get("/status")
async def get_all_status(
    name: list[str] | None = Query(default=None),
    access: ApiAccessContext = Depends(get_api_access_context),
):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager,
        ) = get_services()

        target_names = _unique_names(name)
        if name is not None:
            if not target_names:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "ok": False,
                        "error": "missing_challenge_name",
                    },
                )

            challenges = [
                require_challenge_access(
                    challenge_service.get_challenge(challenge_name),
                    access,
                )
                for challenge_name in target_names
            ]
        else:
            challenges = filter_authorized_challenges(
                challenge_service.list_challenges(),
                access,
            )

        results = [
            _status_payload(config, runtime_service, export_manager, challenge)
            for challenge in challenges
        ]

        return results

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/inspect/{name:path}")
async def inspect_challenge(
    name: str,
    access: ApiAccessContext = Depends(get_api_access_context),
):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager,
        ) = get_services()

        challenge = require_challenge_access(
            challenge_service.get_challenge(name),
            access,
        )

        runtime = runtime_service.status(name)
        extend_availability = build_extend_availability(
            runtime_service,
            config,
            name,
            runtime,
        )

        return {
            "challenge": {
                "name": challenge.name,
                "path": challenge.path,
                "port": challenge.service_port,
                "type": challenge.service_type,
                "enabled": challenge.enabled,
                "created_at": serialize_datetime(challenge.created_at),
            },
            "runtime": {
                "status": runtime.status,
                "container_id": runtime.container_id,
                "remaining_seconds": compute_remaining_seconds(runtime.expires_at),
                "restart_cooldown": runtime_service.check_restart_cooldown(name) or 0,
                "extend_cooldown": get_extend_cooldown(runtime_service, name),
                "extend": extend_availability,
            },
            "exports": safe_exports(export_manager, name, health=True),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
