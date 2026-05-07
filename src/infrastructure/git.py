"""Git repository operations."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Git operation error."""
    pass


class GitRepository:
    """Manage Git repository operations."""

    def __init__(self, repo_url: str, cache_dir: str, branch: str = "main", token: str = ""):
        """Initialize Git repository handler."""
        self.repo_url = repo_url
        self.branch = branch
        self.token = token
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Extract repo name from URL
        self.repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        self.local_path = self.cache_dir / self.repo_name

    def _add_token_to_url(self, url: str) -> str:
        """Add authentication token to repository URL."""
        if not self.token:
            return url

        if url.startswith("https://"):
            # Insert token: https://token@github.com/org/repo.git
            return url.replace("https://", f"https://x-access-token:{self.token}@")
        elif url.startswith("http://"):
            return url.replace("http://", f"http://:{self.token}@")

        return url

    def clone(self) -> Path:
        """Clone repository if not already cached."""
        if self.local_path.exists():
            logger.info(f"Repository already cached at {self.local_path}")
            return self.local_path

        logger.info(f"Cloning repository: {self.repo_url}")

        try:
            url_with_token = self._add_token_to_url(self.repo_url)
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "--branch",
                    self.branch,
                    url_with_token,
                    str(self.local_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise GitError(f"Clone failed: {result.stderr}")

            logger.info(f"Repository cloned successfully")
            return self.local_path

        except subprocess.TimeoutExpired:
            raise GitError("Clone operation timed out")
        except Exception as e:
            raise GitError(f"Clone failed: {str(e)}")

    def pull(self) -> None:
        """Update existing repository."""
        if not self.local_path.exists():
            raise GitError(f"Repository not found at {self.local_path}")

        logger.info(f"Updating repository: {self.repo_name}")

        try:
            result = subprocess.run(
                ["git", "-C", str(self.local_path), "pull", "origin", self.branch],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise GitError(f"Pull failed: {result.stderr}")

            logger.info(f"Repository updated successfully")

        except subprocess.TimeoutExpired:
            raise GitError("Pull operation timed out")
        except Exception as e:
            raise GitError(f"Pull failed: {str(e)}")

    def get_commit_hash(self) -> str:
        """Get current HEAD commit hash."""
        if not self.local_path.exists():
            raise GitError(f"Repository not found at {self.local_path}")

        try:
            result = subprocess.run(
                ["git", "-C", str(self.local_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                raise GitError(f"Failed to get commit hash: {result.stderr}")

            return result.stdout.strip()

        except Exception as e:
            raise GitError(f"Failed to get commit hash: {str(e)}")

    def list_paths(self, subdirectory: str = "") -> list[str]:
        """List all directories in repository."""
        if not self.local_path.exists():
            raise GitError(f"Repository not found at {self.local_path}")

        search_dir = self.local_path / subdirectory if subdirectory else self.local_path
        paths = []

        try:
            for item in search_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    rel_path = item.relative_to(self.local_path)
                    paths.append(str(rel_path).replace("\\", "/"))

            return sorted(paths)

        except Exception as e:
            raise GitError(f"Failed to list paths: {str(e)}")
