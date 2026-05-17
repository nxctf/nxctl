"""Utility functions for the orchestration engine."""

import socket
import os
import signal
import time
from typing import Optional
from pathlib import Path
import json
from nxctl.core.config import get_config

COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"


def green(text: str) -> str:
    return f"{COLOR_GREEN}{text}{COLOR_RESET}"


def red(text: str) -> str:
    return f"{COLOR_RED}{text}{COLOR_RESET}"


def yellow(text: str) -> str:
    return f"{COLOR_YELLOW}{text}{COLOR_RESET}"


def blue(text: str) -> str:
    return f"{COLOR_BLUE}{text}{COLOR_RESET}"


def bold(text: str) -> str:
    return f"{COLOR_BOLD}{text}{COLOR_RESET}"


def get_git_cache_path() -> str:
    """Get the normalized path for git challenge cache."""
    config = get_config()
    cache_dir = Path(config.cache_dir)
    normalized = str(cache_dir).replace("\\", "/").rstrip("/")

    if cache_dir.name == "chall" or normalized.endswith("/chall"):
        return str(cache_dir)

    if normalized in {"./data", "data", "/data"} or normalized.endswith("/data"):
        return str(cache_dir / "chall")

    return str(cache_dir)


def get_challenge_dir(challenge_path: str) -> Path:
    """Get the absolute directory for a challenge based on its relative path."""
    return Path(get_git_cache_path()) / challenge_path


def is_pid_alive(pid: int) -> bool:
    """Return True if PID exists and can receive signal 0."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load_state_file(state_path: Path) -> dict:
    """Load persisted state from JSON file, return empty dict if unavailable."""
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state_file(state_path: Path, state: dict) -> None:
    """Persist state to disk as JSON."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def delete_state_file(state_path: Path) -> None:
    """Delete state file if it exists."""
    try:
        if state_path.exists():
            state_path.unlink()
    except Exception:
        pass


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def find_free_port(start_port: int) -> int:
    """Find the next available port starting from start_port."""
    port = start_port
    max_attempts = 100
    attempts = 0

    while is_port_in_use(port) and attempts < max_attempts:
        port += 1
        attempts += 1

    if attempts >= max_attempts:
        raise RuntimeError(f"Could not find free port starting from {start_port}")

    return port


def kill_process(pid: int, timeout: float = 3.0) -> bool:
    """Kill a process gracefully, using SIGKILL if necessary.

    Returns True if process was killed, False if already dead.
    """
    if not is_pid_alive(pid):
        return False

    try:
        # Try SIGTERM first
        os.kill(pid, signal.SIGTERM)

        # Wait for process to die
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not is_pid_alive(pid):
                return True
            time.sleep(0.2)

        # Force kill with SIGKILL if still alive
        if is_pid_alive(pid):
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            time.sleep(0.5)

        return True
    except Exception:
        return False


def probe_endpoint(url: str, timeout: float = 5.0) -> bool:
    """Best-effort endpoint liveness probe.

    Returns True when endpoint appears online, False when offline/unreachable.
    """
    import urllib.request
    import urllib.error
    import ssl

    # Try with requests library first (with SSL bypass)
    try:
        import requests
        try:
            r = requests.get(url, timeout=timeout, verify=False)
            body = (r.text or "")[:4096]

            # Check for ngrok offline indicators
            if "ERR_NGROK_3200" in body or "is offline" in body.lower():
                return False

            return r.status_code < 500
        except Exception:
            pass
    except ImportError:
        pass

    # Fall back to urllib
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(4096).decode("utf-8", errors="ignore")

            if "ERR_NGROK_3200" in body or "is offline" in body.lower():
                return False

            return resp.status < 500
    except Exception:
        return False
