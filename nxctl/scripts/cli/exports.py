"""CLI command handlers for challenge export management."""

from nxctl.core.constants import EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_PINGGY
from nxctl.scripts.cli.base import (
    get_services,
    red,
    yellow,
)
from nxctl.scripts.cli.render import ERR, box, exports_table, format_error, step_ok, step_warn
from nxctl.scripts.cli.lifecycle import _start_available_exports, _start_with_fallback


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
            print(f"\n{red(ERR)} Challenge not found: {challenge_name}\n")
            return 1

        runtime = runtime_service.status(challenge_name)
        if runtime.status != "running":
            print(f"\n{red(ERR)} Challenge not running\n")
            return 1

        if provider_name:
            provider_name, endpoint = _start_with_fallback(export_manager, challenge_name, challenge, provider_name)
            exports = [{
                "provider": provider_name,
                "type": "tunnel",
                "url": endpoint,
                "status": "running",
                "port": challenge.service_port,
            }]
            failures = []
        else:
            exports, failures = _start_available_exports(export_manager, challenge_name, challenge)

        print()
        print(box("Exports", exports_table(exports), width=116))
        for failure in failures:
            step_warn(f"{failure['provider']} export failed: {format_error(failure['error'])}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Export failed: {str(e)}\n")
        return 1


def cmd_unexport(args) -> int:
    try:
        _, challenge_service, _, export_manager = get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red(ERR)} Challenge not found: {args.name}\n")
            return 1

        exports = export_manager.list_exports(args.name)
        if not exports:
            print(f"\n{yellow('No active exports found')}\n")
            return 0

        for export in exports:
            export_manager.stop_export(args.name, export["provider"], export.get("port") or challenge.service_port)
            step_ok(f"Stopped {export['provider']}")
        print()
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Unexport failed: {str(e)}\n")
        return 1


def cmd_exports(args) -> int:
    try:
        _, _, _, export_manager = get_services()
        exports = export_manager.list_exports()
        if not exports:
            print(f"\n{yellow('No active exports')}\n")
            return 0

        print()
        print(box("Active Exports", exports_table(exports, detailed=True), width=132))
        print()
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Exports list failed: {str(e)}\n")
        return 1
