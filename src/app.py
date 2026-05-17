"""Deprecated launcher for python src/app.py."""

from __future__ import annotations

import sys

from nxctl.app import main


if __name__ == "__main__":
    sys.exit(main())
