"""Challenge catalog and sync routes."""

from fastapi import APIRouter, Depends, HTTPException

from nxctl_api.auth import (
    ApiAccessContext,
    filter_authorized_challenges,
    get_api_access_context,
    verify_admin_secret,
)
from nxctl_api.serializers import (
    serialize_challenge_basic,
    serialize_challenge_with_runtime,
)
from nxctl.core.git import GitRepository
from nxctl.scripts.cli.base import get_services

router = APIRouter()


@router.get("/challenges")
async def list_challenges(
    access: ApiAccessContext = Depends(get_api_access_context),
):
    _, challenge_service, runtime_service, _ = get_services()
    results = []
    challenges = filter_authorized_challenges(
        challenge_service.list_challenges(),
        access,
    )
    for challenge in challenges:
        try:
            runtime = runtime_service.status(challenge.name)
            results.append(serialize_challenge_with_runtime(challenge, runtime))
        except Exception:
            results.append(serialize_challenge_basic(challenge) | {
                "status": "unknown",
                "running": False,
                "remaining_seconds": None,
            })
    return results


@router.get("/list")
async def list_challenges_basic(
    access: ApiAccessContext = Depends(get_api_access_context),
):
    _, challenge_service, _, _ = get_services()
    return [
        serialize_challenge_basic(challenge)
        for challenge in filter_authorized_challenges(
            challenge_service.list_challenges(),
            access,
        )
    ]


@router.post("/sync", dependencies=[Depends(verify_admin_secret)])
async def sync_challenges():
    try:
        config, challenge_service, _, _ = get_services()
        git_repo = GitRepository(
            repo_url=config.github_repo,
            cache_dir=config.chall_dir,
            branch=config.branch,
            token=config.access_token,
        )
        challenges = challenge_service.sync_challenges(git_repo)
        return {
            "ok": True,
            "synced": len(challenges),
            "disabled_stale": getattr(
                challenge_service,
                "last_sync_disabled_stale_count",
                0,
            ),
            "challenges": [
                serialize_challenge_basic(challenge)
                for challenge in challenges
            ],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": "sync_failed",
                "message": str(exc),
            },
        )
