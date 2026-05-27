import sqlite3
import tempfile
from pathlib import Path
import pytest

from nxbcl.launcher.db.connection import init_db, get_db_conn

def test_init_db():
    # Use a temporary directory for test database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_nxbcl.db"
        
        # Initialize
        init_db(db_path)
        
        # Verify tables exist
        expected_tables = {"pow_challenges", "sessions", "instances", "solves", "repos"}
        
        with get_db_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {row["name"] for row in rows}
            
            for t in expected_tables:
                assert t in tables, f"Table {t} should have been created"

def test_db_foreign_keys():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_nxbcl_fk.db"
        init_db(db_path)
        
        with get_db_conn(db_path) as conn:
            # Insert a session
            conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, challenge_id, created_at, expires_at)
                VALUES ('session-1', 'user-1', 'chall-1', '2026-01-01T00:00:00', '2026-01-01T01:00:00')
                """
            )
            # Insert instance referencing session-1
            conn.execute(
                """
                INSERT INTO instances (instance_id, session_id, challenge_id, wallet_address, private_key, status, created_at, expires_at)
                VALUES ('inst-1', 'session-1', 'chall-1', '0x123', '0xabc', 'running', '2026-01-01T00:00:00', '2026-01-01T00:30:00')
                """
            )
            
            # Check instance exists
            row = conn.execute("SELECT COUNT(*) as count FROM instances").fetchone()
            assert row["count"] == 1
            
            # Delete session and ensure cascade deletes instances (foreign_keys constraint verification)
            conn.execute("DELETE FROM sessions WHERE session_id = 'session-1'")
            
        with get_db_conn(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM instances").fetchone()
            assert row["count"] == 0, "Cascade delete did not clean up referenced instances"
