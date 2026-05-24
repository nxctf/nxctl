"""Endpoint health-test routes."""

from fastapi import APIRouter, Depends, HTTPException

from nxctl_api.auth import (
    ApiAccessContext,
    filter_authorized_challenges,
    get_api_access_context,
    require_challenge_access,
)
from nxctl.scripts.cli.base import get_services

router = APIRouter()


@router.get("/test")
async def test_exports(
    name: str | None = None,
    access: ApiAccessContext = Depends(get_api_access_context),
):
    """Read-only endpoint check for active tunnel exports."""
    try:
        _, challenge_service, _, export_manager = get_services()

        if name:
            challenge = require_challenge_access(
                challenge_service.get_challenge(name),
                access,
            )
            results = export_manager.test_tunnel_exports(
                challenge_name=challenge.name,
                mark_unhealthy=False,
            )
        else:
            results = []
            challenges = filter_authorized_challenges(
                challenge_service.list_challenges(),
                access,
            )
            for challenge in challenges:
                results.extend(export_manager.test_tunnel_exports(
                    challenge_name=challenge.name,
                    mark_unhealthy=False,
                ))

        return {
            "ok": True,
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": "endpoint_test_failed",
                "message": str(exc),
            },
        )


@router.post("/test")
async def post_test_exports(
    name: str | None = None,
    access: ApiAccessContext = Depends(get_api_access_context),
):
    return await test_exports(name, access)
