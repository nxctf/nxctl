import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from src.app.utils.db import get_db_conn

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class PowService:
    def __init__(self, db_path: Path, zero_prefix: str = "000", ttl_seconds: int = 120):
        self.db_path = db_path
        self.zero_prefix = zero_prefix
        self.ttl_seconds = ttl_seconds

    def issue_challenge(self, user_id: str, challenge_id: str) -> Dict[str, Any]:
        """Issue a new PoW challenge."""
        token = secrets.token_hex(16)
        salt = secrets.token_hex(8)
        now = utc_now()
        expires_at = now + timedelta(seconds=self.ttl_seconds)

        with get_db_conn(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pow_challenges (token, salt, zero_prefix, user_id, challenge_id, created_at, expires_at, solved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (token, salt, self.zero_prefix, user_id, challenge_id, now.isoformat(), expires_at.isoformat())
            )
        return {
            "challenge_token": token,
            "salt": salt,
            "zero_prefix": self.zero_prefix
        }

    def verify_solution(self, user_id: str, challenge_id: str, token: str, solution: str) -> bool:
        """Verify the PoW solution. Tokens are single-use."""
        now = utc_now()
        now_str = now.isoformat()

        with get_db_conn(self.db_path) as conn:
            # Fetch active challenge
            row = conn.execute(
                """
                SELECT salt, zero_prefix, expires_at
                FROM pow_challenges
                WHERE token = ? AND user_id = ? AND challenge_id = ? AND solved_at IS NULL AND expires_at > ?
                """,
                (token, user_id, challenge_id, now_str)
            ).fetchone()

            if not row:
                return False

            salt = row["salt"]
            zero_prefix = row["zero_prefix"]

            # Compute SHA256 of salt + solution
            hasher = hashlib.sha256()
            hasher.update((salt + solution).encode("utf-8"))
            digest = hasher.hexdigest()

            if not digest.startswith(zero_prefix):
                return False

            # Mark the challenge token as solved
            conn.execute(
                "UPDATE pow_challenges SET solved_at = ? WHERE token = ?",
                (now_str, token)
            )

            # Upsert into solves table
            conn.execute(
                """
                INSERT INTO solves (user_id, challenge_id, solved, solved_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, challenge_id) DO UPDATE SET
                    solved = 1,
                    solved_at = excluded.solved_at
                """,
                (user_id, challenge_id, now_str)
            )
            return True
