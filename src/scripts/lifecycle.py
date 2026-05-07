"""Unified command handlers for the simplified flat CLI."""

import logging
from pathlib import Path
import shutil

from src.core.config import get_config
from src.core.constants import (
    EXPORT_PROVIDER_LOCALTUNNEL,
    EXPORT_PROVIDER_NGROK,
    EXPORT_PROVIDER_PINGGY,
    PROTOCOL_HTTP,
    PROTOCOL_TCP,
)
from src.core.db import init_database, get_db_connection
from src.core.git import GitRepository, GitError
from src.scripts.challenge_service import ChallengeService, ChallengeDiscoveryError
from src.scripts.runtime_service import RuntimeService
from src.scripts.exports.manager import ExportManager

logger = logging.getLogger(__name__)

COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"


def green(text: str) -> str:
    return f"{COLOR_GREEN}{text}{COLOR_RESET}"


def red(text: str) -> str:
    return f"{COLOR_RED}{text}{COLOR_RESET}"


def yellow(text: str) -> str:
    return f"{COLOR_YELLOW}{text}{COLOR_RESET}"


def blue(text: str) -> str:
    return f"{COLOR_BLUE}{text}{COLOR_RESET}"


def bold(text: str) -> str:
    return f"{COLOR_BOLD}{text}{COLOR_RESET}"


def _get_git_cache_path(config) -> str:
    repo_name = config.github_repo.rstrip("/").split("/")[-1].replace(".git", "")
    return f"{config.cache_dir}/{repo_name}"


def _get_services():
    config = get_config()
    init_database(config.db_file)
    challenge_service = ChallengeService(config.db_file)
    runtime_service = RuntimeService(config.db_file, _get_git_cache_path(config))
    export_manager = ExportManager(config, config.db_file)
    return config, challenge_service, runtime_service, export_manager


def _provider_priority(service_type: str) -> list[str]:
    if service_type == PROTOCOL_TCP:
        return [EXPORT_PROVIDER_PINGGY, EXPORT_PROVIDER_NGROK]
    return [EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL]


def _start_with_fallback(export_manager, challenge_name: str, challenge, provider_name: str | None = None) -> tuple[str, str]:
    providers = [provider_name] if provider_name else _provider_priority(challenge.service_type)
    last_error = None

    for provider in providers:
        if not provider:
            continue
        try:
            endpoint = export_manager.start_export(
                challenge_name=challenge_name,
                host_port=challenge.service_port,
                protocol=challenge.service_type,
                provider_name=provider,
            )
            return provider, endpoint
        except Exception as exc:
            last_error = exc
            logger.warning("Provider %s failed for %s: %s", provider, challenge_name, exc)

    if last_error:
        raise last_error
    raise RuntimeError("No export provider available")


def cmd_sync(args) -> int:
    try:
        config, challenge_service, _, _ = _get_services()
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
        _, challenge_service, _, _ = _get_services()
        challenges = challenge_service.list_challenges()
        if not challenges:
            print(f"\n{yellow('No challenges found')}\n")
            return 0

        print(f"\n{bold('Challenges')}\n{'-' * 96}")
        print(f"{'Name':28} {'Type':5} {'Port':6} {'State':8} Path")
        print(f"{'-' * 96}")
        for challenge in challenges:
            status = green('on') if challenge.enabled else red('off')
            if args.all:
                print(f"{challenge.name:28} {challenge.service_type:5} {str(challenge.service_port):6} {status:8} {challenge.path}")
            else:
                print(f"{challenge.name:28} {challenge.service_type:5} {str(challenge.service_port):6} {status:8} {challenge.path}")
        print(f"{'-' * 96}\n")
        print()
        return 0
    except Exception as e:
        print(f"\n{red('✗')} List failed: {str(e)}\n")
        return 1


def cmd_inspect(args) -> int:
    try:
        _, challenge_service, _, _ = _get_services()
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
        _, challenge_service, _, _ = _get_services()
        challenge = challenge_service.add_challenge(args.name, args.path, args.port, args.type)
        print(f"\n{green('✓')} Added challenge: {challenge.name}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Add failed: {str(e)}\n")
        return 1


def cmd_remove(args) -> int:
    try:
        _, challenge_service, _, _ = _get_services()
        if not challenge_service.remove_challenge(args.name):
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1
        print(f"\n{green('✓')} Removed challenge: {args.name}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Remove failed: {str(e)}\n")
        return 1


def cmd_enable(args) -> int:
    try:
        _, challenge_service, _, _ = _get_services()
        for name in args.name:
            challenge_service.enable_challenge(name)
            print(f"{green('✓')} Enabled: {name}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Enable failed: {str(e)}\n")
        return 1


def cmd_disable(args) -> int:
    try:
        _, challenge_service, _, _ = _get_services()
        for name in args.name:
            challenge_service.disable_challenge(name)
            print(f"{green('✓')} Disabled: {name}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Disable failed: {str(e)}\n")
        return 1


def cmd_up(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = _get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1

        if not challenge.enabled:
            challenge_service.enable_challenge(args.name)
            challenge = challenge_service.get_challenge(args.name)

        print(f"\n{blue('Starting...')}")
        runtime_service.start(args.name)
        challenge = challenge_service.get_challenge(args.name) or challenge
        print(f"{green('✓')} Started")

        print(f"{blue('Auto-exporting...')}")
        provider, endpoint = _start_with_fallback(export_manager, args.name, challenge)

        print(f"{green('✓')} Exported via {provider}")
        print(f"  Endpoint: {endpoint}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Up failed: {str(e)}\n")
        return 1


def cmd_down(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = _get_services()
        challenge = challenge_service.get_challenge(args.name)

        print(f"\n{blue('Stopping...')}")
        if challenge:
            exports = export_manager.list_exports(args.name)
            for export in exports:
                export_manager.stop_export(args.name, export["provider"], challenge.service_port)
                print(f"{green('✓')} Stopped {export['provider']} export")
            runtime_service.stop(args.name)
            print(f"{green('✓')} Stopped container")
        else:
            print(f"{yellow('No challenge found, skipping container stop')}")

        print(f"{green('✓')} Down complete\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Down failed: {str(e)}\n")
        return 1


def cmd_restart(args) -> int:
    if cmd_down(args) != 0:
        return 1
    return cmd_up(args)


def cmd_status(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = _get_services()
        challenges = [challenge_service.get_challenge(args.name)] if args.name else challenge_service.list_challenges()
        challenges = [challenge for challenge in challenges if challenge]

        if not challenges:
            print(f"\n{yellow('No challenges found')}\n")
            return 0

        print(f"\n{bold('Status')}\n{'-' * 104}")
        print(f"{'Challenge':28} {'Runtime':10} {'Port':6} {'Export':12} Endpoint")
        print(f"{'-' * 104}")

        for challenge in challenges:
            runtime = runtime_service.status(challenge.name)
            exports = export_manager.list_exports(challenge.name)
            export_label = exports[0]["provider"] if exports else "-"
            endpoint = exports[0]["endpoint"] if exports else "-"
            runtime_label = green('running') if runtime.status == 'running' else red(runtime.status)
            challenge_label = green('✓') if runtime.status == 'running' else red('✗')
            print(f"{challenge_label} {challenge.name:26} {runtime_label:10} {str(challenge.service_port):6} {export_label:12} {endpoint}")

        print(f"{'-' * 104}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Status failed: {str(e)}\n")
        return 1


def cmd_export(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = _get_services()
        provider_names = {EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_PINGGY}

        if getattr(args, "name", None) is None:
            challenge_name = args.target
            provider_name = None
        elif args.target in provider_names:
            provider_name = args.target
            challenge_name = args.name
        else:
            challenge_name = args.target
            provider_name = None

        challenge = challenge_service.get_challenge(challenge_name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {challenge_name}\n")
            return 1

        runtime = runtime_service.status(challenge_name)
        if runtime.status != "running":
            print(f"\n{red('✗')} Challenge not running\n")
            return 1

        if provider_name:
            provider_name, endpoint = _start_with_fallback(export_manager, challenge_name, challenge, provider_name)
        else:
            provider_name, endpoint = _start_with_fallback(export_manager, challenge_name, challenge)

        print(f"\n{green('✓')} Exported via {provider_name}")
        print(f"  Endpoint: {endpoint}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Export failed: {str(e)}\n")
        return 1


def cmd_unexport(args) -> int:
    try:
        _, challenge_service, _, export_manager = _get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1

        exports = export_manager.list_exports(args.name)
        if not exports:
            print(f"\n{yellow('No active exports found')}\n")
            return 0

        for export in exports:
            export_manager.stop_export(args.name, export["provider"], challenge.service_port)
            print(f"{green('✓')} Stopped {export['provider']}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Unexport failed: {str(e)}\n")
        return 1


def cmd_exports(args) -> int:
    try:
        _, _, _, export_manager = _get_services()
        exports = export_manager.list_exports()
        if not exports:
            print(f"\n{yellow('No active exports')}\n")
            return 0

        print(f"\n{bold('Active Exports')}\n{'-' * 104}")
        print(f"{'Challenge':28} {'Provider':12} {'Protocol':8} {'Port':6} Endpoint")
        print(f"{'-' * 104}")
        for export in exports:
            print(f"{export['challenge']:28} {export['provider']:12} {export['protocol']:8} {str(export['port']):6} {export['endpoint']}")
        print(f"{'-' * 104}\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Exports list failed: {str(e)}\n")
        return 1


def cmd_clean(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = _get_services()
        challenge = challenge_service.get_challenge(args.name)
        if challenge:
            for export in export_manager.list_exports(args.name):
                export_manager.stop_export(args.name, export["provider"], challenge.service_port)
            runtime_service.stop(args.name)

            challenge_dir = Path(config.cache_dir) / Path(config.github_repo.rstrip("/").split("/")[-1].replace(".git", "")) / challenge.path
            run_file = challenge_dir / "docker-compose.run.yml"
            if run_file.exists():
                run_file.unlink()

            if args.data:
                data_dir = Path("data") / args.name.replace("/", "_")
                if data_dir.exists():
                    shutil.rmtree(data_dir)

        print(f"\n{green('✓')} Clean complete\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Clean failed: {str(e)}\n")
        return 1


def cmd_prune(args) -> int:
    try:
        _, _, _, export_manager = _get_services()
        deleted = export_manager.prune_inactive(provider_name=args.provider)
        print(f"\n{green('✓')} Pruned {deleted} inactive export records\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Prune failed: {str(e)}\n")
        return 1
