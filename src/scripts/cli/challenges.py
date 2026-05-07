"""CLI command handlers for challenge management."""

import logging
from src.core.git import GitRepository, GitError
from src.scripts.challenge_service import ChallengeDiscoveryError
from src.scripts.cli.base import (
    get_services,
    green,
    red,
    yellow,
    blue,
    bold,
)

logger = logging.getLogger(__name__)


def cmd_sync(args) -> int:
    try:
        config, challenge_service, _, _ = get_services()
        git_repo = GitRepository(
            repo_url=config.github_repo,
            cache_dir=config.cache_dir,
            branch=config.branch,
            token=config.access_token,
        )

        print(f"\n{blue('Syncing challenges...')}")
        challenges = challenge_service.sync_challenges(git_repo)
        print(f"{green('✓')} Synced {len(challenges)} challenges\n")
        for challenge in challenges:
            print(f"  • {challenge.name} ({challenge.service_type}:{challenge.service_port})")
        print()
        return 0
    except GitError as e:
        print(f"\n{red('✗')} Sync failed: {str(e)}\n")
        return 1
    except ChallengeDiscoveryError as e:
        print(f"\n{red('✗')} Sync failed: {str(e)}\n")
        return 1
    except Exception as e:
        print(f"\n{red('✗')} Sync failed: {str(e)}\n")
        return 1


def cmd_list(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        challenges = challenge_service.list_challenges()
        if not challenges:
            print(f"\n{yellow('No challenges found')}\n")
            return 0

        print(f"\n{bold('Challenges')}")
        print(f"{'-' * 100}")
        print(f"{'Name':28} {'Type':8} {'Port':8} {'Path'}")
        print(f"{'-' * 100}")
        for challenge in challenges:
            print(f"{challenge.name:28} {challenge.service_type:8} {str(challenge.service_port):8} {challenge.path}")
        print(f"{'-' * 100}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} List failed: {str(e)}\n")
        return 1


def cmd_inspect(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1

        print(f"\n{bold(f'Challenge: {challenge.name}')}\n{'-' * 60}")
        print(f"Path:      {challenge.path}")
        print(f"Port:      {challenge.service_port}")
        print(f"Type:      {challenge.service_type}")
        print(f"Enabled:   {green('Yes') if challenge.enabled else red('No')}")
        print(f"Created:   {challenge.created_at}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Inspect failed: {str(e)}\n")
        return 1


def cmd_add(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        challenge = challenge_service.add_challenge(args.name, args.path, args.port, args.type)
        print(f"\n{green('✓')} Added challenge: {challenge.name}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Add failed: {str(e)}\n")
        return 1


def cmd_remove(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        if not challenge_service.remove_challenge(args.name):
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1
        print(f"\n{green('✓')} Removed challenge: {args.name}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Remove failed: {str(e)}\n")
        return 1
