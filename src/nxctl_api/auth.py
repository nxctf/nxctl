"""API authentication helpers."""

from dataclasses import dataclass
import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from nxctl.core.access import access_key_matches
from nxctl.core.config import get_config

API_KEY_NAME = "X-NXCTL-Token"
AUTHORIZATION_HEADER = "Authorization"
ADMIN_SECRET_HEADER = "X-NXCTL-Admin-Secret"
CHALLENGE_KEY_HEADER = "X-NXCTL-Challenge-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
authorization_header = APIKeyHeader(name=AUTHORIZATION_HEADER, auto_error=False)
admin_secret_header = APIKeyHeader(name=ADMIN_SECRET_HEADER, auto_error=False)
challenge_key_header = APIKeyHeader(name=CHALLENGE_KEY_HEADER, auto_error=False)


@dataclass(frozen=True)
class ApiAccessContext:
    """Request-scoped API authorization context."""

    challenge_keys: list[str]
    admin: bool = False


def _config_value(name: str) -> str:
    try:
        return str(getattr(get_config(), name, "") or "").strip()
    except Exception:
        return ""


def _bearer_token(header_value: str | None) -> str:
    if not header_value:
        return ""
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def get_api_token() -> str:
    return (
        os.getenv("NXCTL_API_TOKEN")
        or _config_value("api_token")
        or ""
    ).strip()


def get_api_admin_secret() -> str:
    return (
        os.getenv("NXCTL_API_ADMIN_SECRET")
        or _config_value("api_admin_secret")
        or ""
    ).strip()


async def verify_client_token(
    api_key: str = Depends(api_key_header),
    authorization: str = Depends(authorization_header),
):
    """Validate normal API access when api_token is configured."""
    expected_token = get_api_token()

    if not expected_token:
        return None

    submitted_token = (api_key or "").strip() or _bearer_token(authorization)
    if not hmac.compare_digest(submitted_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "ok": False,
                "error": "invalid_or_missing_api_token",
            },
        )

    return submitted_token


async def verify_admin_secret(
    _client_token: str | None = Depends(verify_client_token),
    admin_secret: str = Depends(admin_secret_header),
):
    """Validate admin-only permission for dangerous/global actions."""
    expected_secret = get_api_admin_secret()

    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "ok": False,
                "error": "api_admin_secret_not_configured",
            },
        )

    if not hmac.compare_digest((admin_secret or "").strip(), expected_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "ok": False,
                "error": "invalid_or_missing_admin_secret",
            },
        )

    return True


def is_admin_secret_valid(admin_secret: str | None) -> bool:
    """Return True when the optional admin override secret is valid."""
    expected_secret = get_api_admin_secret()
    submitted_secret = (admin_secret or "").strip()
    return bool(expected_secret and submitted_secret) and hmac.compare_digest(
        submitted_secret,
        expected_secret,
    )


def parse_challenge_keys(header_value: str | None) -> list[str]:
    """Parse one or more submitted challenge keys from a request header."""
    raw = str(header_value or "")
    return [part.strip() for part in raw.split(",") if part.strip()]


async def get_api_access_context(
    _client_token: str | None = Depends(verify_client_token),
    challenge_key: str = Depends(challenge_key_header),
    admin_secret: str = Depends(admin_secret_header),
) -> ApiAccessContext:
    """Validate base API access and collect optional scoped credentials."""
    return ApiAccessContext(
        challenge_keys=parse_challenge_keys(challenge_key),
        admin=is_admin_secret_valid(admin_secret),
    )


def challenge_requires_key(challenge) -> bool:
    return bool(str(getattr(challenge, "access_key_hash", "") or "").strip())


def can_access_challenge(challenge, access: ApiAccessContext) -> bool:
    """Return True when request credentials can access a challenge."""
    if access.admin:
        return True

    stored_hash = str(getattr(challenge, "access_key_hash", "") or "").strip()
    if not stored_hash:
        return True

    return any(
        access_key_matches(stored_hash, submitted_key)
        for submitted_key in access.challenge_keys
    )


def filter_authorized_challenges(challenges, access: ApiAccessContext):
    """Hide challenges that are not authorized for the request."""
    return [
        challenge
        for challenge in challenges
        if can_access_challenge(challenge, access)
    ]


def raise_challenge_not_found_or_unauthorized():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "ok": False,
            "error": "challenge_not_found_or_not_authorized",
        },
    )


def require_challenge_access(
    challenge,
    access: ApiAccessContext,
    require_enabled: bool = True,
):
    """Raise a non-enumerating 404 unless credentials can access challenge."""
    if (
        not challenge
        or (require_enabled and not bool(getattr(challenge, "enabled", True)))
        or not can_access_challenge(challenge, access)
    ):
        raise_challenge_not_found_or_unauthorized()
    return challenge
