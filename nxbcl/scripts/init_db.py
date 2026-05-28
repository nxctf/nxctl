import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.app.utils.config import get_nxbcl_config
from src.app.utils.db import init_db

def main():
    print("Initializing NXBCL launcher directories and database...")
    config = get_nxbcl_config()

    # Ensure all directories exist
    config.data_path.mkdir(parents=True, exist_ok=True)
    config.chall_dir.mkdir(parents=True, exist_ok=True)
    config.locks_dir.mkdir(parents=True, exist_ok=True)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.tmp_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Data root: {config.data_path}")
    print(f"DB file:   {config.db_file}")

    # Initialize DB schema
    init_db(config.db_file)
    print("Database initialized successfully.")

if __name__ == "__main__":
    main()
