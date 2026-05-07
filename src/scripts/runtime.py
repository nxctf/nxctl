"""CLI command handlers for runtime management."""

import logging
from src.core.config import get_config
from src.core.db import init_database
from src.scripts.runtime_service import RuntimeService, RuntimeError

logger = logging.getLogger(__name__)


def _get_git_cache_path(config):
    """Extract repo name from config URL and build cache path."""
    cache_dir = Path(config.cache_dir)
    normalized = str(cache_dir).replace("\\", "/").rstrip("/")

    if cache_dir.name == "chall" or normalized.endswith("/chall"):
        return str(cache_dir)

    if normalized in {"./data", "data", "/data"} or normalized.endswith("/data"):
        return str(cache_dir / "chall")

    return str(cache_dir)


def cmd_runtime_build(args) -> int:
    """Command: runtime build <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Build runtime with correct repo path
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

        # Start runtime
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

        # Stop runtime
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
    """Command: runtime status [name]"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        git_cache_path = _get_git_cache_path(config)
        runtime_service = RuntimeService(config.db_file, git_cache_path)

        if challenge_name:
            # Single challenge status
            runtime = runtime_service.status(challenge_name)

            print(f"\n{'='*60}")
            print(f"Challenge: {challenge_name}")
            print(f"{'='*60}")
            print(f"Status:       {runtime.status}")
            print(f"Container ID: {runtime.container_id}")
            print(f"Public URL:   {runtime.public_url or 'N/A'}")
            print(f"Started at:   {runtime.started_at or 'N/A'}")
            print()

        else:
            # All challenges status
            from src.scripts.challenge_service import ChallengeService
            challenge_service = ChallengeService(config.db_file)
            challenges = challenge_service.list_challenges()

            if not challenges:
                print("\nNo challenges found.\n")
                return 0

            print(f"\n{'='*80}")
            print(f"Runtime Status for {len(challenges)} challenges")
            print(f"{'='*80}")
            print(f"{'Name':<30} | {'Status':<10} | {'Port':<6} | {'Container':<15}")
            print(f"{'-'*80}")

            for challenge in challenges:
                runtime = runtime_service.status(challenge.name)
                container = (runtime.container_id or "N/A")[:15]
                print(f"{challenge.name:<30} | {runtime.status:<10} | {challenge.service_port:<6} | {container:<15}")

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


def cmd_runtime_force_stop(args) -> int:
    """Command: runtime force-stop [name] [--all]"""
    try:
        config = get_config()
        challenge_name = args.name
        force_all = getattr(args, 'all', False)

        # Initialize database
        init_database(config.db_file)

        git_cache_path = _get_git_cache_path(config)
        runtime_service = RuntimeService(config.db_file, git_cache_path)

        if force_all:
            # Stop all challenges
            from src.scripts.challenge_service import ChallengeService
            challenge_service = ChallengeService(config.db_file)
            challenges = challenge_service.list_challenges()

            print(f"\n✓ Stopping all {len(challenges)} challenges...")
            stopped_count = 0

            for challenge in challenges:
                try:
                    runtime_service.stop(challenge.name)
                    stopped_count += 1
                except Exception as e:
                    logger.warning(f"Failed to stop {challenge.name}: {e}")

            print(f"  Stopped: {stopped_count}/{len(challenges)} challenges")
            print()

        elif challenge_name:
            # Stop single challenge
            runtime_service.stop(challenge_name)
            print(f"\n✓ Challenge force-stopped: {challenge_name}\n")

        else:
            print("\n✗ Either specify a challenge name or use --all\n")
            return 1

        return 0

    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        print(f"\n✗ Runtime error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1
