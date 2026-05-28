#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root and src/ directory to python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.app.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
