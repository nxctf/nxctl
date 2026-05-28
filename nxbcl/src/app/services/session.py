import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from src.app.utils.db import get_db_conn

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class SessionService:
    def __init__(self, db_path: Path, ttl_seconds: int = 86400):
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds

    def create_session(self, user_id: str, challenge_id: str) -> str:
        """Create a new session for a user and challenge, returning the session token."""
        session_id = secrets.token_hex(32)
        now = utc_now()
        expires_at = now + timedelta(seconds=self.ttl_seconds)

        created_str = now.isoformat()
        expires_str = expires_at.isoformat()

        with get_db_conn(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, challenge_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, challenge_id, created_str, expires_str)
            )
        return session_id

    def validate_session(self, session_id: str, challenge_id: str) -> Optional[Dict[str, Any]]:
        """Validate if a session ID is valid, matches challenge_id, and is not expired."""
        now_str = utc_now().isoformat()
        with get_db_conn(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT session_id, user_id, challenge_id, created_at, expires_at
                FROM sessions
                WHERE session_id = ? AND challenge_id = ? AND expires_at > ?
                """,
                (session_id, challenge_id, now_str)
            ).fetchone()

            if row:
                return dict(row)
        return None

    def sweep_expired(self) -> int:
        """Delete all expired sessions."""
        now_str = utc_now().isoformat()
        with get_db_conn(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (now_str,)
            )
            return cursor.rowcount
