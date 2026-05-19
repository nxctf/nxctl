"""Utility functions for the orchestration engine."""

import socket
import os
import signal
import time
from typing import Optional
from pathlib import Path
import json
import tempfile
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
    return str(config.chall_dir)


def get_challenge_dir(challenge_path: str) -> Path:
    """Get the absolute directory for a challenge based on its relative path."""
    return Path(get_git_cache_path()) / challenge_path


def safe_runtime_name(name: str) -> str:
    """Return a filesystem-safe name for runtime artifacts."""
    safe = str(name or "").replace("\\", "_").replace("/", "_").replace(":", "_")
    return safe.strip("._") or "unknown"


def get_runtime_dir(config=None) -> Path:
    config = config or get_config()
    path = config.runtime_dir.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_export_state_dir(config=None) -> Path:
    config = config or get_config()
    path = config.state_dir.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_export_logs_dir(config=None, provider: str = "") -> Path:
    config = config or get_config()
    path = config.export_logs_dir.resolve()
    if provider:
        path = path / safe_runtime_name(provider)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_tmp_dir(config=None) -> Path:
    config = config or get_config()
    path = config.tmp_dir.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_challenge_locks_dir(config=None) -> Path:
    config = config or get_config()
    path = config.locks_dir.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_compose_dir(config=None) -> Path:
    config = config or get_config()
    path = config.compose_dir.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_pid_alive(pid: int) -> bool:
    """Return True if PID exists and can receive signal 0."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_json_file(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_state_file(state_path: Path, legacy_paths: Optional[list[Path]] = None, migrate: bool = True) -> dict:
    """Load persisted state from JSON, optionally migrating legacy state."""
    state_path = Path(state_path)
    if state_path.exists():
        return _read_json_file(state_path)

    for legacy_path in legacy_paths or []:
        legacy_path = Path(legacy_path)
        if not legacy_path.exists():
            continue
        state = _read_json_file(legacy_path)
        if not state:
            continue
        if migrate:
            try:
                save_state_file(state_path, state)
                legacy_path.unlink()
            except Exception:
                pass
        return state

    return {}


def save_state_file(state_path: Path, state: dict) -> None:
    """Persist state to disk as JSON using an atomic same-directory replace."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{state_path.name}.",
        suffix=".tmp",
        dir=str(state_path.parent),
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, state_path)
        try:
            dir_fd = os.open(str(state_path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            pass
    except Exception:
        try:
            temp_path.unlink()
        except Exception:
            pass
        raise


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


class ChallengeLock:
    """A cross-process file lock for a challenge to prevent race conditions between daemon and CLI."""
    def __init__(self, challenge_name: str, config_or_path=None):
        self.challenge_name = challenge_name
        if config_or_path is not None and hasattr(config_or_path, "locks_dir"):
            locks_dir = get_challenge_locks_dir(config_or_path)
        elif config_or_path is not None:
            locks_dir = Path(config_or_path)
            if locks_dir.name not in {"locks", "challenges"}:
                locks_dir = locks_dir / "locks"
            locks_dir.mkdir(parents=True, exist_ok=True)
        else:
            locks_dir = get_challenge_locks_dir()
        self.lock_file = locks_dir / f"{safe_runtime_name(challenge_name)}.lock"
        self.fd = None

    def __enter__(self):
        try:
            self.fd = open(self.lock_file, "a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt
                # Lock 1 byte exclusively and block until acquired
                self.fd.seek(0)
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX)

            metadata = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "timestamp": int(time.time()),
                "challenge": self.challenge_name,
                "status": "acquired",
            }
            self.fd.seek(0)
            self.fd.truncate()
            json.dump(metadata, self.fd, ensure_ascii=True, indent=2)
            self.fd.write("\n")
            self.fd.flush()
            os.fsync(self.fd.fileno())
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to acquire lock for challenge %s: %s", self.challenge_name, e)
            if self.fd:
                try:
                    self.fd.close()
                except Exception:
                    pass
                self.fd = None
            raise RuntimeError(f"Failed to acquire challenge lock for {self.challenge_name}: {e}") from e
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd:
            try:
                released_at = int(time.time())
                metadata = {
                    "pid": os.getpid(),
                    "hostname": socket.gethostname(),
                    "timestamp": released_at,
                    "challenge": self.challenge_name,
                    "status": "released",
                    "released_at": released_at,
                }
                self.fd.seek(0)
                self.fd.truncate()
                json.dump(metadata, self.fd, ensure_ascii=True, indent=2)
                self.fd.write("\n")
                self.fd.flush()
                os.fsync(self.fd.fileno())

                if os.name == "nt":
                    import msvcrt
                    self.fd.seek(0)
                    msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            finally:
                try:
                    self.fd.close()
                except Exception:
                    pass
                self.fd = None
