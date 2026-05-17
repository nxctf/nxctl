"""Database initialization and management."""

import sqlite3
from pathlib import Path
from typing import Optional


def init_database(db_path: str) -> None:
    """Initialize SQLite database with schema."""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create challenges table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            path TEXT NOT NULL,
            service_port INTEGER NOT NULL,
            service_type TEXT DEFAULT 'http',
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create runtime_instances table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runtime_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            status TEXT DEFAULT 'stopped',
            container_id TEXT,
            tunnel_provider TEXT,
            public_url TEXT,
            started_at TIMESTAMP,
            expires_at TIMESTAMP,
            last_activity TIMESTAMP,
            last_revert TIMESTAMP,
            last_restart DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (challenge_id) REFERENCES challenges(id)
        )
    """)

    # Create challenge_exports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            runtime_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            export_type TEXT DEFAULT 'tunnel',
            protocol TEXT,
            target_port INTEGER,
            public_endpoint TEXT,
            pid INTEGER,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (runtime_id) REFERENCES runtime_instances(id)
        )
    """)

    conn.commit()

    # Migration: Add pid column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE challenge_exports ADD COLUMN pid INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add export_type column for direct vs tunnel exports
    try:
        cursor.execute("ALTER TABLE challenge_exports ADD COLUMN export_type TEXT DEFAULT 'tunnel'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add last_restart column to runtime_instances
    try:
        cursor.execute("ALTER TABLE runtime_instances ADD COLUMN last_restart DATETIME")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.close()


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def close_db_connection(conn: sqlite3.Connection) -> None:
    """Close database connection."""
    if conn:
        conn.close()
