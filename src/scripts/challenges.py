"""CLI command handlers for challenge management."""

import logging
from src.core.config import get_config
from src.core.db import init_database
from src.core.git import GitRepository, GitError
from src.scripts.challenge_service import ChallengeService, ChallengeDiscoveryError

logger = logging.getLogger(__name__)


def cmd_challenge_sync(args) -> int:
    """Command: challenge sync"""
    try:
        config = get_config()

        # Initialize database
        init_database(config.db_file)
        logger.info(f"Database initialized: {config.db_file}")

        # Create Git repository handler
        git_repo = GitRepository(
            repo_url=config.github_repo,
            cache_dir=config.cache_dir,
            branch=config.branch,
            token=config.access_token,
        )

        # Clone/update repository
        if git_repo._is_git_repository(git_repo.local_path):
            repo_path = git_repo.local_path
            git_repo.pull()
        else:
            repo_path = git_repo.clone()

        logger.info(f"Repository synced: {repo_path}")

        # Discover and save challenges
        challenge_service = ChallengeService(config.db_file)
        challenges = challenge_service.sync_challenges(git_repo)

        print(f"\n✓ Synced {len(challenges)} challenges from repository")
        for challenge in challenges:
            print(f"  • {challenge.name} (port {challenge.service_port}, type {challenge.service_type})")

        return 0

    except GitError as e:
        logger.error(f"Git error: {str(e)}")
        print(f"\n✗ Git error: {str(e)}", flush=True)
        return 1

    except ChallengeDiscoveryError as e:
        logger.error(f"Discovery error: {str(e)}")
        print(f"\n✗ Discovery error: {str(e)}", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_challenge_list(args) -> int:
    """Command: challenge list"""
    try:
        config = get_config()

        # Initialize database
        init_database(config.db_file)

        # List challenges
        challenge_service = ChallengeService(config.db_file)
        challenges = challenge_service.list_challenges()

        if not challenges:
            print("\nNo challenges found. Run 'challenge sync' first.\n")
            return 0

        print(f"\nTotal: {len(challenges)} challenges\n")
        print("Name                          | Port | Type   | Path")
        print("-" * 70)

        for challenge in challenges:
            name = challenge.name[:28].ljust(28)
            port = str(challenge.service_port).ljust(4)
            service_type = challenge.service_type.ljust(6)
            path = challenge.path
            print(f"{name} | {port} | {service_type} | {path}")

        print()
        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_challenge_inspect(args) -> int:
    """Command: challenge inspect <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Get challenge
        challenge_service = ChallengeService(config.db_file)
        challenge = challenge_service.get_challenge(challenge_name)

        if not challenge:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        print(f"\n{'='*60}")
        print(f"Challenge: {challenge.name}")
        print(f"{'='*60}")
        print(f"Path:         {challenge.path}")
        print(f"Port:         {challenge.service_port}")
        print(f"Type:         {challenge.service_type}")
        print(f"Enabled:      {challenge.enabled}")
        print(f"Created:      {challenge.created_at}")
        print()

        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_challenge_add(args) -> int:
    """Command: challenge add <name> <path> <port> [--type]"""
    try:
        config = get_config()

        # Initialize database
        init_database(config.db_file)

        # Add challenge
        challenge_service = ChallengeService(config.db_file)
        challenge = challenge_service.add_challenge(
            name=args.name,
            path=args.path,
            port=args.port,
            service_type=args.type,
        )

        print(f"\n✓ Challenge added successfully")
        print(f"  Name:  {challenge.name}")
        print(f"  Path:  {challenge.path}")
        print(f"  Port:  {challenge.service_port}")
        print(f"  Type:  {challenge.service_type}")
        print()

        return 0

    except ChallengeDiscoveryError as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_challenge_remove(args) -> int:
    """Command: challenge remove <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Remove challenge
        challenge_service = ChallengeService(config.db_file)
        removed = challenge_service.remove_challenge(challenge_name)

        if not removed:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        print(f"\n✓ Challenge removed: {challenge_name}\n")
        return 0

    except ChallengeDiscoveryError as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_challenge_enable(args) -> int:
    """Command: challenge enable <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Enable challenge
        challenge_service = ChallengeService(config.db_file)
        enabled = challenge_service.enable_challenge(challenge_name)

        if not enabled:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        print(f"\n✓ Challenge enabled: {challenge_name}\n")
        return 0

    except ChallengeDiscoveryError as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1


def cmd_challenge_disable(args) -> int:
    """Command: challenge disable <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        # Initialize database
        init_database(config.db_file)

        # Disable challenge
        challenge_service = ChallengeService(config.db_file)
        disabled = challenge_service.disable_challenge(challenge_name)

        if not disabled:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        print(f"\n✓ Challenge disabled: {challenge_name}\n")
        return 0

    except ChallengeDiscoveryError as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n", flush=True)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n✗ Error: {str(e)}", flush=True)
        return 1
