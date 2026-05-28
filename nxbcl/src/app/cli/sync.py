import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.app.utils.config import get_nxbcl_config, file_lock
from src.app.utils.db import get_db_conn

def sync(dry_run: bool = False) -> int:
    config = get_nxbcl_config()

    if not config.enabled:
        print("NXBCL is disabled in config.yml.")
        return 1

    repo_url = config.git_repo
    branch = config.git_branch
    token = config.git_access_token

    if not repo_url:
        print("Error: git.repo is not configured in config.yml under nxbcl.")
        return 1

    print(f"Syncing blockchain challenges from: {repo_url} (branch: {branch})")

    if dry_run:
        print(f"[DRY-RUN] Would sync {repo_url} (branch: {branch}) to {config.chall_dir}")
        return 0

    # Acquire lock for syncing
    lock_path = config.locks_dir / "sync.lock"

    try:
        with file_lock(lock_path):
            try:
                from nxctl.core.git import GitRepository
                print("Using nxctl GitRepository helper.")

                # nxctl's GitRepository resolves its local path internally.
                # If we pass config.chall_dir, it will clone there.
                git_repo = GitRepository(
                    repo_url=repo_url,
                    cache_dir=str(config.chall_dir),
                    branch=branch,
                    token=token
                )

                local_path = git_repo.clone()
                if local_path.exists():
                    try:
                        git_repo.pull()
                    except Exception as e:
                        print(f"Warning during pull: {e}")

                commit_sha = git_repo.get_commit_hash()
            except ImportError:
                print("nxctl git helper not available. Shelling out to git CLI.")
                import subprocess
                dest_dir = config.chall_dir

                if dest_dir.exists() and (dest_dir / ".git").exists():
                    print(f"Pulling in {dest_dir}")
                    subprocess.run(["git", "-C", str(dest_dir), "pull", "origin", branch], check=True)
                else:
                    print(f"Cloning to {dest_dir}")
                    if dest_dir.exists() and any(dest_dir.iterdir()):
                        raise RuntimeError(
                            f"{dest_dir} exists but is not a git repository. "
                            "Move or clear it before syncing."
                        )
                    dest_dir.parent.mkdir(parents=True, exist_ok=True)
                    if dest_dir.exists():
                        dest_dir.rmdir()
                    subprocess.run(["git", "clone", "--depth=1", "--branch", branch, repo_url, str(dest_dir)], check=True)

                res = subprocess.run(["git", "-C", str(dest_dir), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
                commit_sha = res.stdout.strip()

            # Log clone/sync event to database
            with get_db_conn(config.db_file) as conn:
                conn.execute(
                    """
                    INSERT INTO repos (repo_url, branch, commit_sha, synced_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(repo_url) DO UPDATE SET
                        branch = excluded.branch,
                        commit_sha = excluded.commit_sha,
                        synced_at = excluded.synced_at
                    """,
                    (repo_url, branch, commit_sha, datetime.now(timezone.utc).isoformat())
                )

            print(f"Sync complete. Cached commit SHA: {commit_sha}")
            return 0

    except TimeoutError:
        print("Error: Could not acquire sync lock. Another sync operation might be running.")
        return 1
    except Exception as e:
        print(f"Error during sync: {e}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync blockchain challenges.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run sync.")
    args = parser.parse_args()
    sys.exit(sync(dry_run=args.dry_run))
