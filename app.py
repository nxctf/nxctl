#!/usr/bin/env python3
"""NXCTL launcher entry point."""

import os
import sys
import subprocess
import signal
import termios
import tty
from pathlib import Path

PREFIX_INFO = f"\033[32mINFO\033[0m"
PREFIX_ERROR = f"\033[31m[ERROR]\033[0m"

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
PROJECT_PATH = SRC_ROOT / "nxctl"

def disable_input():
    """Disable input terminal temporarily."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return old_settings

def flush_stdin():
    try:
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass

def restore_input(old_settings):
    """Restore input terminal."""
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def main():
    if not PROJECT_PATH.exists():
        print(f"{PREFIX_ERROR} Project path tidak ditemukan: {PROJECT_PATH}")
        return 1

    os.chdir(PROJECT_ROOT)
    os.environ["PYTHONPATH"] = (
        f"{SRC_ROOT}{os.pathsep}{os.environ['PYTHONPATH']}"
        if os.environ.get("PYTHONPATH")
        else str(SRC_ROOT)
    )
    args = sys.argv[1:] if len(sys.argv) > 1 else ["--help"]

    # Handle Ctrl+C gracefully
    def handle_sigint(sig, frame):
        print(f"\n{PREFIX_INFO} Dihentikan oleh user (Ctrl+C)")
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_sigint)

    # Disable input user
    old_settings = disable_input()
    try:
        result = subprocess.run([sys.executable, "-m", "nxctl.app"] + args)
        return result.returncode
    finally:
        # Restore input terminal
        flush_stdin()
        restore_input(old_settings)

if __name__ == "__main__":
    sys.exit(main())
