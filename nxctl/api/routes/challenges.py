"""Challenge catalog and sync routes."""

from fastapi import APIRouter, Depends, HTTPException

from nxctl.api.auth import verify_admin_secret, verify_client_token
from nxctl.api.serializers import (
    serialize_challenge_basic,
    serialize_challenge_with_runtime,
)
from nxctl.core.git import GitRepository
from nxctl.scripts.cli.base import get_services

router = APIRouter()


@router.get("/challenges", dependencies=[Depends(verify_client_token)])
async def list_challenges():
    _, challenge_service, runtime_service, _ = get_services()
    results = []
    for challenge in challenge_service.list_challenges():
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


@router.get("/list", dependencies=[Depends(verify_client_token)])
async def list_challenges_basic():
    _, challenge_service, _, _ = get_services()
    return [
        serialize_challenge_basic(challenge)
        for challenge in challenge_service.list_challenges()
    ]


@router.post("/sync", dependencies=[Depends(verify_admin_secret)])
async def sync_challenges():
    try:
        config, challenge_service, _, _ = get_services()
        git_repo = GitRepository(
            repo_url=config.github_repo,
            cache_dir=config.cache_dir,
            branch=config.branch,
            token=config.access_token,
        )
        challenges = challenge_service.sync_challenges(git_repo)
        return {
            "ok": True,
            "synced": len(challenges),
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
