import logging
import os
import subprocess
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Git operation error."""
    pass


class GitRepository:
    """Manage Git repository operations."""

    def __init__(self, repo_url: str, cache_dir: str, branch: str = "main", token: str = ""):
        self.repo_url = repo_url
        self.branch = branch
        self.token = token

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Determine a stable local_path for cloning. New callers pass the
        # explicit challenge directory; older callers may pass a data/cache root.
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        normalized = str(self.cache_dir).replace("\\", "/").rstrip("/")
        if self.cache_dir.name == "chall" or normalized.endswith("/chall"):
            # cache_dir is already the challenge folder
            self.local_path = self.cache_dir
            self.repo_name = repo_name
        elif normalized in {"./data", "data", "/data"} or normalized.endswith("/data"):
            # cache_dir may be the generic data root; use its challenge subdirectory.
            self.repo_name = "chall"
            self.local_path = self.cache_dir / "chall"
        else:
            # default: use cache_dir/<repo_name>
            self.repo_name = repo_name
            self.local_path = self.cache_dir / self.repo_name

    def _add_token_to_url(self, url: str) -> str:
        if not self.token:
            return url

        if url.startswith("https://"):
            return url.replace(
                "https://",
                f"https://x-access-token:{self.token}@"
            )

        if url.startswith("http://"):
            return url.replace(
                "http://",
                f"http://:{self.token}@"
            )

        return url

    def _is_git_repository(self, path: Path) -> bool:
        if not path.exists():
            return False

        # Check for .git directory or file (submodule)
        if not (path / ".git").exists():
            return False

        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            return (
                result.returncode == 0
                and result.stdout.strip().lower() == "true"
            )

        except Exception:
            return False

    def clone(self) -> Path:
        """Clone repository.

        Flow:
        1. try public clone
        2. if auth fail -> retry with token
        """

        if self._is_git_repository(self.local_path):
            logger.info(f"Repository already cached at {self.local_path}")
            return self.local_path

        # remove broken cache
        if self.local_path.exists():
            shutil.rmtree(self.local_path, ignore_errors=True)

        git_path = shutil.which("git")

        if not git_path:
            raise GitError("git executable not found")

        def run_clone(url: str):
            cmd = [
                git_path,
                "clone",
                "--depth=1",
                "--branch",
                self.branch,
                url,
                str(self.local_path),
            ]

            logger.info(f"Running: {' '.join(cmd)}")

            # Use GIT_TERMINAL_PROMPT=0 to prevent hanging on authentication prompts
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"

            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env
            )

        # FIRST TRY: public clone
        try:
            result = run_clone(self.repo_url)

        except subprocess.TimeoutExpired:
            raise GitError("Clone timeout")

        if result.returncode == 0:
            logger.info("Public clone success")
            return self.local_path

        stderr = (result.stderr or "").lower()

        auth_error = any(
            x in stderr
            for x in [
                "authentication failed",
                "permission denied",
                "could not read",
                "repository not found",
            ]
        )

        # non-auth failure
        if not auth_error:
            raise GitError(result.stderr)

        # no token available
        if not self.token:
            raise GitError(
                f"Authentication required but no token provided:\n{result.stderr}"
            )

        # SECOND TRY: token clone
        token_url = self._add_token_to_url(self.repo_url)

        try:
            result = run_clone(token_url)

        except subprocess.TimeoutExpired:
            raise GitError("Clone with token timeout")

        if result.returncode != 0:
            raise GitError(
                f"Clone with token failed:\n{result.stderr}"
            )

        logger.info("Private clone success")
        return self.local_path

    def pull(self):
        if not self._is_git_repository(self.local_path):
            raise GitError(f"Invalid repository: {self.local_path}")

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.local_path),
                "pull",
                "origin",
                self.branch,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )

        if result.returncode != 0:
            raise GitError(result.stderr)

        logger.info("Repository updated successfully")

    def get_commit_hash(self) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.local_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            raise GitError(result.stderr)

        return result.stdout.strip()

    def list_paths(self, subdirectory: str = "") -> list[str]:
        search_dir = (
            self.local_path / subdirectory
            if subdirectory
            else self.local_path
        )

        if not search_dir.exists():
            return []

        paths = []

        for item in search_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                rel = item.relative_to(self.local_path)
                paths.append(str(rel).replace("\\", "/"))

        return sorted(paths)
