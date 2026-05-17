"""Endpoint health-test routes."""

from fastapi import APIRouter, Depends, HTTPException

from nxctl.api.auth import verify_client_token
from nxctl.scripts.cli.base import get_services

router = APIRouter()


@router.get("/test", dependencies=[Depends(verify_client_token)])
async def test_exports(name: str | None = None):
    """Read-only endpoint check for active tunnel exports."""
    try:
        _, challenge_service, _, export_manager = get_services()

        if name and not challenge_service.get_challenge(name):
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "error": "challenge_not_found",
                },
            )

        results = export_manager.test_tunnel_exports(
            challenge_name=name,
            mark_unhealthy=False,
        )
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


@router.post("/test", dependencies=[Depends(verify_client_token)])
async def post_test_exports(name: str | None = None):
    return await test_exports(name)
