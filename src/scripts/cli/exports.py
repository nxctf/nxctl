"""CLI command handlers for challenge export management."""

import logging
from src.core.constants import EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_PINGGY, EXPORT_PROVIDERS
from src.scripts.cli.base import (
    get_services,
    green,
    red,
    yellow,
    blue,
    bold,
)
from src.scripts.cli.lifecycle import _start_with_fallback

logger = logging.getLogger(__name__)


def cmd_export(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
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
        _, challenge_service, _, export_manager = get_services()
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
        _, _, _, export_manager = get_services()
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
