"""CLI command handlers for challenge export management."""

from nxctl.core.constants import EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_PINGGY
from nxctl.scripts.cli.base import (
    get_services,
    green,
    red,
    yellow,
)
from nxctl.scripts.cli.render import ERR, OK, box, exports_table, format_error, step_ok, step_warn, table
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


def cmd_test(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        challenge_name = getattr(args, "name", None)

        if challenge_name and not challenge_service.get_challenge(challenge_name):
            print(f"\n{red(ERR)} Challenge not found: {challenge_name}\n")
            return 1

        results = export_manager.test_tunnel_exports(challenge_name, mark_unhealthy=True)
        killed = export_manager.sweep_orphan_tunnel_processes()

        healed_exports = []
        heal_failures = []
        affected_names = {
            result.get("challenge")
            for result in results
            if not result.get("reachable") and result.get("challenge")
        }
        if challenge_name:
            affected_names.add(challenge_name)
        else:
            for challenge in challenge_service.list_challenges():
                if runtime_service.status(challenge.name).status != "running":
                    continue
                active_exports = export_manager.list_exports(challenge.name, check_health=False)
                has_tunnel = any(
                    export.get("type") != "direct"
                    and export.get("provider") != "base_ip"
                    for export in active_exports
                )
                if not has_tunnel:
                    affected_names.add(challenge.name)

        for name in sorted(affected_names):
            try:
                challenge = challenge_service.get_challenge(name)
                if not challenge or runtime_service.status(name).status != "running":
                    continue
                ports = challenge_service.list_challenge_ports(name)
                exports, failures = _start_available_exports(export_manager, name, challenge, ports)
                for export in exports:
                    export["challenge"] = name
                healed_exports.extend(exports)
                heal_failures.extend(failures)
            except Exception as exc:
                heal_failures.append({
                    "provider": "auto-heal",
                    "error": str(exc),
                })

        if not results and not healed_exports and not heal_failures:
            if killed:
                print(f"\n{yellow(f'Cleaned orphan tunnel processes: {killed}')}")
            print(f"\n{yellow('No tunnel exports to test')}\n")
            return 0

        rows = []
        failed = 0
        for result in results:
            reachable = bool(result.get("reachable"))
            if not reachable:
                failed += 1
            rows.append([
                result.get("challenge") or "-",
                result.get("provider") or "-",
                result.get("type") or "-",
                result.get("port_label") or result.get("port") or "-",
                green(f"{OK} Reachable") if reachable else red(f"{ERR} Unreachable"),
                f"{result.get('latency_ms', 0)}ms",
                result.get("url") or result.get("endpoint") or "-",
                format_error(result.get("error"), width=60) if not reachable else "-",
            ])

        print()
        if rows:
            print(box(
                "Endpoint Test",
                table(
                    ["Challenge", "Provider", "Type", "Port", "Result", "Latency", "URL", "Error"],
                    rows,
                    [24, 14, 8, 12, 14, 10, 54, 36],
                ),
                width=150,
            ))
        else:
            print(yellow("No existing tunnel exports to test; checking auto-heal candidates."))
        if killed:
            print(f"\n{yellow(f'Cleaned orphan tunnel processes: {killed}')}")
        if healed_exports:
            healed_rows = []
            for export in healed_exports:
                healed_rows.append([
                    export.get("challenge") or "-",
                    export.get("provider") or "-",
                    export.get("type") or "-",
                    export.get("port_label") or export.get("port") or "-",
                    export.get("status") or "-",
                    export.get("pid") or "-",
                    export.get("url") or export.get("endpoint") or "-",
                ])
            print(box(
                "Auto-Heal Actions",
                table(
                    ["Challenge", "Provider", "Type", "Port", "Status", "PID", "URL"],
                    healed_rows,
                    [24, 14, 8, 12, 10, 8, 58],
                ),
                width=142,
            ))
        for failure in heal_failures:
            step_warn(f"{failure['provider']} heal failed: {format_error(failure['error'])}")
        print()
        return 1 if failed else 0
    except Exception as e:
        print(f"\n{red(ERR)} Endpoint test failed: {str(e)}\n")
        return 1
