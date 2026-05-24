"""Challenge access-key helpers."""

import hashlib
import hmac

ACCESS_KEY_FILENAMES = ("key",)
ACCESS_KEY_HASH_PREFIX = "sha256:"


def normalize_access_key(value: str | None) -> str:
    """Normalize a submitted or file-backed challenge access key."""
    return str(value or "").strip()


def hash_access_key(value: str | None) -> str:
    """Hash a challenge access key for storage."""
    normalized = normalize_access_key(value)
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{ACCESS_KEY_HASH_PREFIX}{digest}"


def access_key_matches(stored_hash: str | None, submitted_key: str | None) -> bool:
    """Return True when a submitted key matches a stored key hash."""
    stored = str(stored_hash or "").strip()
    if not stored:
        return True
    submitted_hash = hash_access_key(submitted_key)
    return bool(submitted_hash) and hmac.compare_digest(stored, submitted_hash)
