"""CLI commands for runtime management."""

import logging
import subprocess
from pathlib import Path

from src.infrastructure.config import get_config
from src.infrastructure.database import init_database, get_db_connection, close_db_connection
from src.services.runtime_service import RuntimeService, RuntimeError

logger = logging.getLogger(__name__)


def _get_git_cache_path(config):
    """Extract repo name from config URL and build cache path."""
    repo_name = config.github_repo.rstrip("/").split("/")[-1].replace(".git", "")
    return f"{config.cache_dir}/{repo_name}"


def cmd_runtime_build(args) -> int:
    """Command: runtime build <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Build runtime with correct repo path (cache_dir/repo_name)
        git_cache_path = _get_git_cache_path(config)
        runtime_service = RuntimeService(config.db_file, git_cache_path)
        image_name = runtime_service.build(challenge_name)

        print(f"\n✓ Image built successfully")
        print(f"  Challenge:  {challenge_name}")
        print(f"  Image:      {image_name}")
        print()

        return 0

    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        print(f"\n✗ Runtime error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_runtime_start(args) -> int:
    """Command: runtime start <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Start runtime with correct repo path (cache_dir/repo_name)
        git_cache_path = _get_git_cache_path(config)
        runtime_service = RuntimeService(config.db_file, git_cache_path)
        runtime = runtime_service.start(challenge_name)

        print(f"\n✓ Challenge started successfully")
        print(f"  Challenge:    {challenge_name}")
        print(f"  Status:       {runtime.status}")
        print(f"  Container ID: {runtime.container_id}")
        if runtime.started_at:
            print(f"  Started at:   {runtime.started_at}")
        print()

        return 0

    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        print(f"\n✗ Runtime error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_runtime_stop(args) -> int:
    """Command: runtime stop <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Stop runtime with correct repo path (cache_dir/repo_name)
        git_cache_path = _get_git_cache_path(config)
        runtime_service = RuntimeService(config.db_file, git_cache_path)
        runtime_service.stop(challenge_name)

        print(f"\n✓ Challenge stopped successfully")
        print(f"  Challenge: {challenge_name}")
        print()

        return 0

    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        print(f"\n✗ Runtime error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_runtime_status(args) -> int:
    """Command: runtime status [name] - show status of one or all challenges"""
    try:
        config = get_config()
        challenge_name = args.name if args.name else None

        # Initialize database
        init_database(config.db_file)

        # Get status with correct repo path (cache_dir/repo_name)
        git_cache_path = _get_git_cache_path(config)
        runtime_service = RuntimeService(config.db_file, git_cache_path)

        if challenge_name:
            # Show status of single challenge
            runtime = runtime_service.status(challenge_name)

            print(f"\nRuntime Status: {challenge_name}")
            print(f"  Status:       {runtime.status}")
            if runtime.container_id:
                print(f"  Container ID: {runtime.container_id}")
            if runtime.started_at:
                print(f"  Started at:   {runtime.started_at}")
            if runtime.public_url:
                print(f"  Public URL:   {runtime.public_url}")
            print()
        else:
            print("\nNote: Specify a challenge name to see detailed status")
            print("Usage: python app.py runtime status <name>")
            print()

        return 0

    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        print(f"\n✗ Runtime error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def _compose_down_force(challenge_dir: Path, docker_compose: Path) -> None:
    """Force stop containers using docker compose (v2 fallback v1)."""
    # Check for run-specific compose file
    docker_compose_run = challenge_dir / "docker-compose.run.yml"
    target_compose = docker_compose_run if docker_compose_run.exists() else docker_compose

    if not target_compose.exists():
        return

    cmd_v2 = ["docker", "compose", "-f", str(target_compose), "down", "--remove-orphans", "-v"]
    cmd_v1 = ["docker-compose", "-f", str(target_compose), "down", "--remove-orphans", "-v"]

    try:
        subprocess.run(cmd_v2, cwd=str(challenge_dir), capture_output=True, text=True, timeout=90, check=True)
        return
    except FileNotFoundError:
        pass
    except subprocess.CalledProcessError:
        pass

    subprocess.run(cmd_v1, cwd=str(challenge_dir), capture_output=True, text=True, timeout=90, check=False)


def cmd_runtime_force_stop(args) -> int:
    """Command: runtime force-stop <name> | --all"""
    conn = None
    try:
        config = get_config()
        init_database(config.db_file)

        challenge_name = getattr(args, "name", None)
        stop_all = bool(getattr(args, "all", False))
        if not stop_all and not challenge_name:
            raise RuntimeError("Specify challenge name or use --all")

        git_cache_path = _get_git_cache_path(config)
        conn = get_db_connection(config.db_file)
        cur = conn.cursor()

        if stop_all:
            cur.execute("SELECT id, name, path FROM challenges")
        else:
            cur.execute("SELECT id, name, path FROM challenges WHERE name = ?", (challenge_name,))

        rows = cur.fetchall()
        if not rows:
            raise RuntimeError("No matching challenges found")

        total = 0
        stopped = 0
        for row in rows:
            total += 1
            chall_id = row["id"]
            chall_name = row["name"]
            chall_path = row["path"]

            # 1) force remove known running containers from DB
            cur.execute(
                "SELECT container_id FROM runtime_instances WHERE challenge_id = ? AND status = 'running' AND container_id IS NOT NULL AND container_id != ''",
                (chall_id,),
            )
            cids = [r[0] for r in cur.fetchall()]
            for cid in cids:
                try:
                    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True, timeout=30, check=False)
                except Exception:
                    pass

            # 2) best effort compose down to clean network/leftovers
            challenge_dir = (Path(git_cache_path) / chall_path).resolve()
            docker_compose = challenge_dir / "docker-compose.yml"
            docker_compose_run = challenge_dir / "docker-compose.run.yml"
            target_compose = docker_compose_run if docker_compose_run.exists() else docker_compose

            if target_compose.exists():
                try:
                    _compose_down_force(challenge_dir, target_compose)
                except Exception:
                    pass

            # 3) update DB status
            cur.execute(
                "UPDATE runtime_instances SET status = 'stopped' WHERE challenge_id = ? AND status = 'running'",
                (chall_id,),
            )
            if cur.rowcount > 0:
                stopped += 1

        conn.commit()

        print("\n✓ Force stop completed")
        print(f"  Targets:         {total}")
        print(f"  Updated stopped: {stopped}")
        print()
        return 0

    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        print(f"\n✗ Runtime error: {str(e)}\n", flush=True)
        return 1
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n", flush=True)
        return 1
    finally:
        if conn:
            close_db_connection(conn)
