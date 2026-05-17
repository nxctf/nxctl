"""API authentication helpers."""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from nxctl.core.config import get_config

API_KEY_NAME = "X-NXCTL-Token"
AUTHORIZATION_HEADER = "Authorization"
ADMIN_SECRET_HEADER = "X-NXCTL-Admin-Secret"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
authorization_header = APIKeyHeader(name=AUTHORIZATION_HEADER, auto_error=False)
admin_secret_header = APIKeyHeader(name=ADMIN_SECRET_HEADER, auto_error=False)


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
    if submitted_token != expected_token:
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

    if (admin_secret or "").strip() != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "ok": False,
                "error": "invalid_or_missing_admin_secret",
            },
        )

    return True
