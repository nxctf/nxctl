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
    def __init__(self, config_path: str = "config.yml"):
        # Resolve config path
        self.config_path = Path(config_path).resolve()
        if not self.config_path.exists():
            # Try walking up or check in current working directory
            self.config_path = Path("config.yml").resolve()

        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        else:
            raw = {}
        
        # Substitute environment variables
        self.raw = substitute_env_vars(raw)
        self.nxbcl_raw = self.raw.get("nxbcl", {})
        
        self.enabled = bool(self.nxbcl_raw.get("enabled", True))
        self.data_dir = self.nxbcl_raw.get("data_dir", "./data_nxbcl")
        
        git = self.nxbcl_raw.get("git", {})
        self.git_repo = git.get("repo", "")
        self.git_branch = git.get("branch", "main")
        self.git_access_token = git.get("access_token", os.environ.get("GITHUB_TOKEN", ""))
        
        pow_cfg = self.nxbcl_raw.get("pow", {})
        self.pow_zero_prefix = pow_cfg.get("zero_prefix", "000")
        
        session = self.nxbcl_raw.get("session", {})
        self.session_ttl_seconds = int(session.get("ttl_seconds", 86400))
        self.instance_ttl_seconds = int(session.get("instance_ttl_seconds", 1800))
        
        limits = self.nxbcl_raw.get("limits", {})
        self.max_concurrent = int(limits.get("max_concurrent", 5))
        
        nxctl_cfg = self.nxbcl_raw.get("nxctl", {})
        sync_cfg = nxctl_cfg.get("sync", {})
        self.sync_enabled = bool(sync_cfg.get("enabled", True))
        self.sync_mode = sync_cfg.get("mode", "git")
        
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

# Global config helper
_config_instance = None

def get_nxbcl_config(config_path: str = "config.yml") -> NXBCLConfig:
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

