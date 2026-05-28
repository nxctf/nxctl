import os
import yaml
from pathlib import Path
from typing import Any, Dict

try:
    from nxctl.core.config import substitute_env_vars
except ImportError:
    # Fallback env substitution if not running in nxctl path
    import re
    def substitute_env_vars(value: Any) -> Any:
        if isinstance(value, str):
            def replace_env(match):
                var_name = match.group(1)
                return os.environ.get(var_name, "")
            return re.sub(r"\$\{([A-Z0-9_]+)\}", replace_env, value)
        if isinstance(value, dict):
            return {k: substitute_env_vars(v) for k, v in value.items()}
        if isinstance(value, list):
            return [substitute_env_vars(item) for item in value]
        return value

# Load .env manually if not already done
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class NXBCLConfig:
    def __init__(self, config_path: str = "nxbcl.yml"):
        # Resolve config path
        self.config_path = Path(config_path).resolve()
        if not self.config_path.exists():
            # Try package-relative path
            pkg_relative = (Path(__file__).resolve().parent.parent / "nxbcl.yml").resolve()
            if pkg_relative.exists():
                self.config_path = pkg_relative
            else:
                # Try walking up or check in root workspace directories
                self.config_path = Path("nxbcl.yml").resolve()
                if not self.config_path.exists():
                    self.config_path = Path("nxbcl/nxbcl.yml").resolve()
                    if not self.config_path.exists():
                        self.config_path = Path("nxbcl/config.yml").resolve()
                        if not self.config_path.exists():
                            self.config_path = Path("config.yml").resolve()

        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        else:
            raw = {}

        # Substitute environment variables
        self.raw = substitute_env_vars(raw)
        # If 'nxbcl' key is present, use it; otherwise the whole raw dictionary is nxbcl config
        self.nxbcl_raw = self.raw.get("nxbcl", self.raw)
        self.enabled = True
        app_cfg = self.nxbcl_raw.get("app", {})
        self.data_dir = app_cfg.get("data_dir", self.nxbcl_raw.get("data_dir", "./data_nxbcl"))
        self.panel_base_ip = app_cfg.get("base_ip", "")
        git = self.nxbcl_raw.get("git", {})
        self.git_repo = git.get("repo", "")
        self.git_branch = git.get("branch", "main")
        self.git_access_token = git.get("access_token", os.environ.get("GITHUB_TOKEN", ""))

        pow_cfg = self.nxbcl_raw.get("pow", {})
        self.pow_zero_prefix = pow_cfg.get("zero_prefix", "000")

        session = self.nxbcl_raw.get("session", {})
        self.session_ttl_seconds = int(session.get("ttl_seconds", 86400))
        self.instance_ttl_seconds = int(session.get("instance_ttl_seconds", 600))

        # Challenge TTL configuration
        challenge_cfg = self.nxbcl_raw.get("challenge", {})
        self.challenge_ttl_seconds = int(challenge_cfg.get("ttl_seconds", 600))
        self.challenge_extend_seconds = int(challenge_cfg.get("extend_seconds", 300))
        self.challenge_extend_threshold_seconds = int(challenge_cfg.get("extend_threshold_seconds", 300))

        # RPC TTL configuration
        rpc_cfg = self.nxbcl_raw.get("rpc", {})
        self.rpc_base_ip = rpc_cfg.get("base_ip", self.panel_base_ip)
        self.rpc_ttl_seconds = int(rpc_cfg.get("ttl_seconds", 1200))
        self.rpc_extend_seconds = int(rpc_cfg.get("extend_seconds", 600))
        self.rpc_extend_threshold_seconds = int(rpc_cfg.get("extend_threshold_seconds", 600))

        limits = self.nxbcl_raw.get("limits", {})
        self.max_concurrent = int(limits.get("max_concurrent", 5))

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve()

    @property
    def db_file(self) -> Path:
        return self.data_path / "nxbcl.db"

    @property
    def chall_dir(self) -> Path:
        return self.data_path / "chall"

    @property
    def locks_dir(self) -> Path:
        return self.data_path / "runtime" / "locks"

    @property
    def state_dir(self) -> Path:
        return self.data_path / "runtime" / "state"

    @property
    def tmp_dir(self) -> Path:
        return self.data_path / "tmp"

    @property
    def logs_dir(self) -> Path:
        return self.data_path / "logs"

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        value = str(value or "").strip().rstrip("/")
        if not value:
            return ""
        if "://" in value:
            return value
        return f"http://{value}"

    @property
    def panel_base_url(self) -> str:
        return self._normalize_base_url(self.panel_base_ip)

    @property
    def rpc_base_url(self) -> str:
        return self._normalize_base_url(self.rpc_base_ip)

# Global config helper
_config_instance = None

def get_nxbcl_config(config_path: str = "nxbcl.yml") -> NXBCLConfig:
    global _config_instance
    if _config_instance is None:
        _config_instance = NXBCLConfig(config_path)
    return _config_instance

import time
from contextlib import contextmanager

@contextmanager
def file_lock(lock_path: Path, timeout: float = 10.0):
    """Simple, cross-platform file locking using directory creation."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    while True:
        try:
            lock_path.mkdir(exist_ok=False)
            break
        except FileExistsError:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Could not acquire lock on {lock_path} within {timeout} seconds")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock_path.rmdir()
        except Exception:
            pass
