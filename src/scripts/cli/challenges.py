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
        config, challenge_service, runtime_service, export_manager = get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1

        print(f"\n{bold(f'Challenge: {challenge.name}')}\n{'-' * 80}")
        print(f"{'Path:':12} {challenge.path}")
        print(f"{'Port:':12} {challenge.service_port}")
        print(f"{'Type:':12} {challenge.service_type}")
        print(f"{'Enabled:':12} {green('Yes') if challenge.enabled else red('No')}")
        print(f"{'Created:':12} {challenge.created_at}")

        # Runtime Info
        runtime = runtime_service.status(args.name)
        print(f"\n{bold('Runtime Status')}")
        print(f"{'-' * 40}")
        status_col = green(runtime.status) if runtime.status == 'running' else red(runtime.status)
        print(f"{'Status:':12} {status_col}")

        if runtime.status == 'running':
            print(f"{'Container:':12} {runtime.container_id or '-'}")
            print(f"{'Started At:':12} {runtime.started_at or '-'}")

            if runtime.expires_at:
                from datetime import datetime
                remaining = runtime.expires_at - datetime.now()
                rem_seconds = remaining.total_seconds()
                if rem_seconds > 0:
                    rem_str = f"{int(rem_seconds // 60)}m {int(rem_seconds % 60)}s"
                    print(f"{'Expires At:':12} {runtime.expires_at} ({rem_str} left)")
                else:
                    print(f"{'Expires At:':12} {runtime.expires_at} ({red('EXPIRED')})")

        # Cooldown Info
        cooldown = runtime_service.check_restart_cooldown(args.name)
        if cooldown:
            print(f"{'Restart CD:':12} {yellow(f'In cooldown ({cooldown}s left)')}")
        elif runtime.status == 'running':
            print(f"{'Restart CD:':12} {green('Ready')}")

        # Exports Info
        exports = export_manager.list_exports(args.name, check_health=True)
        print(f"\n{bold('Active Exports')}")
        print(f"{'-' * 40}")
        if not exports:
            print("  None")
        for exp in exports:
            exp_status = green('✓ active') if exp['status'] == 'active' else red(f"✗ {exp['status']}")
            print(f"  • {bold(exp['provider']):10} [{exp_status}]")
            print(f"    Endpoint:  {exp['endpoint']}")
            print(f"    PID:       {exp['pid']}")
            print(f"    Created:   {exp['created_at']}")

        print(f"\n{'-' * 80}\n")
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
