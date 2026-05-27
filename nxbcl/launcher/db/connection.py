import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

class DBConnectionError(Exception):
    pass

@contextmanager
def get_db_conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield a database connection with WAL mode enabled and autocommit/transaction handling."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise DBConnectionError(f"Database transaction failed: {e}") from e
    finally:
        conn.close()

def init_db(db_path: Path, schema_path: Path = None) -> None:
    """Initialize the database with schema.sql."""
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent / "schema.sql"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found at {schema_path}")
        
    with open(schema_path, "r", encoding="utf-8") as f:
        ddl = f.read()
        
    with get_db_conn(db_path) as conn:
        conn.executescript(ddl)
