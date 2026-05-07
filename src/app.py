#!/usr/bin/env python3
"""Top-level entry point for the project.
It forwards command‑line arguments to the original root ``app.py``
implementation, preserving existing behaviour while providing a tidy
``src/app.py`` location.
"""

import sys
from pathlib import Path

# Ensure the repository root is on ``sys.path`` so the original ``app.py`` can be imported.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Import the original ``main`` function.
from app import main as _original_main

def main(argv: list | None = None) -> int:
    """Delegate to the original ``app.main``.

    Args:
        argv: Optional list of arguments (defaults to ``sys.argv[1:]``).
    Returns:
        Exit code from the original application.
    """
    if argv is None:
        argv = sys.argv[1:]
    return _original_main(argv)

if __name__ == "__main__":
    sys.exit(main())
