"""Status and inspect routes."""

from fastapi import APIRouter, Depends, HTTPException

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


@router.get("/status")
async def get_all_status(
    access: ApiAccessContext = Depends(get_api_access_context),
):
    try:
        (
            config,
            challenge_service,
            runtime_service,
            export_manager,
        ) = get_services()

        results = []
        challenges = filter_authorized_challenges(
            challenge_service.list_challenges(),
            access,
        )
        for challenge in challenges:
            runtime = runtime_service.status(challenge.name)
            extend_availability = build_extend_availability(
                runtime_service,
                config,
                challenge.name,
                runtime,
            )
            results.append({
                "name": challenge.name,
                "status": runtime.status,
                "container_id": runtime.container_id,
                "remaining_seconds": compute_remaining_seconds(runtime.expires_at),
                "restart_cooldown": runtime_service.check_restart_cooldown(challenge.name) or 0,
                "extend_cooldown": get_extend_cooldown(runtime_service, challenge.name),
                "extend": extend_availability,
                "exports": safe_exports(export_manager, challenge.name, health=False),
            })

        return results

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
