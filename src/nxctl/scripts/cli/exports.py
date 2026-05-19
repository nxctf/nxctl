"""CLI command handlers for challenge export management."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from nxctl.core.constants import EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_PINGGY
from nxctl.core.utils import (
    get_challenge_locks_dir,
    get_export_logs_dir,
    get_export_state_dir,
    get_runtime_tmp_dir,
)
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


def _list_tunnel_processes() -> str:
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (result.stderr or "").strip()

    lines = [
        line
        for line in result.stdout.splitlines()
        if "pinggy" in line or "ngrok" in line or "lt --port" in line
    ]
    return "\n".join(lines)


def _kill_by_pattern(pattern: str) -> None:
    subprocess.run(
        ["pkill", "-9", "-f", pattern],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _kill_zombie_parents() -> int:
    killed = 0
    result = subprocess.run(
        ["ps", "-eo", "pid,ppid,stat,cmd"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return killed

    parent_pids: set[int] = set()
    for line in result.stdout.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        _, ppid, stat, cmd = parts
        if "Z" in stat and ("pinggy" in cmd or "ngrok" in cmd):
            try:
                parent_pid = int(ppid)
            except ValueError:
                continue
            if parent_pid > 1 and parent_pid != os.getpid():
                parent_pids.add(parent_pid)

    for parent_pid in parent_pids:
        try:
            os.kill(parent_pid, signal.SIGKILL)
            killed += 1
        except ProcessLookupError:
            pass
        except PermissionError:
            pass
        except Exception:
            pass

    return killed


def _remove_pycache_dirs(root: Path) -> int:
    removed = 0
    for path in sorted(root.rglob("__pycache__"), key=lambda item: len(item.parts), reverse=True):
        if not path.is_dir():
            continue
        try:
            shutil.rmtree(path)
            removed += 1
        except Exception:
            pass
    return removed


def _remove_path(path: Path) -> bool:
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        else:
            return False
        return True
    except Exception:
        return False


def _clear_dir_children(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0

    removed = 0
    for child in path.iterdir():
        if _remove_path(child):
            removed += 1
    return removed


def _clear_matching_files(root: Path, patterns: list[str]) -> int:
    if not root.exists() or not root.is_dir():
        return 0

    removed = 0
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and _remove_path(path):
                removed += 1
    return removed


def _cleanup_export_artifacts(config) -> dict[str, int]:
    """Remove known runtime artifacts without deleting the whole legacy exports dir."""
    legacy_exports_dir = Path(config.exports_dir)
    counts = {
        "state": _clear_dir_children(get_export_state_dir(config)),
        "logs": _clear_dir_children(get_export_logs_dir(config)),
        "locks": _clear_dir_children(get_challenge_locks_dir(config)),
        "tmp": _clear_dir_children(get_runtime_tmp_dir(config)),
    }

    legacy_state_dirs = (
        config.legacy_export_state_dirs()
        if hasattr(config, "legacy_export_state_dirs")
        else [legacy_exports_dir]
    )
    for legacy_state_dir in legacy_state_dirs:
        counts["state"] += _clear_matching_files(legacy_state_dir, ["*.json"])
    counts["logs"] += _clear_matching_files(legacy_exports_dir, ["*.log"])
    counts["tmp"] += _clear_matching_files(legacy_exports_dir, ["ngrok_*.yml"])

    legacy_logs_dir = legacy_exports_dir / "logs"
    legacy_locks_dir = legacy_exports_dir / "locks"
    counts["logs"] += _clear_dir_children(legacy_logs_dir)
    counts["locks"] += _clear_dir_children(legacy_locks_dir)
    return counts


def cmd_ps(args) -> int:
    try:
        config, _, _, export_manager = get_services()

        if getattr(args, "kill", False):
            _kill_by_pattern("pinggy")
            _kill_by_pattern("lt --port")
            _kill_by_pattern("ngrok")
            time.sleep(2)

            zombie_parents = _kill_zombie_parents()
            time.sleep(1)

            try:
                export_manager.mark_all_exports_inactive()
            except Exception:
                pass

            pycache_count = _remove_pycache_dirs(Path("."))
            cleanup_counts = _cleanup_export_artifacts(config)

            step_ok("Killed pinggy/ngrok/localtunnel processes")
            if zombie_parents:
                step_ok(f"Killed zombie parent processes: {zombie_parents}")
            step_ok(f"Removed __pycache__ directories: {pycache_count}")
            step_ok(f"Cleared export state entries: {cleanup_counts['state']}")
            step_ok(f"Cleared export logs: {cleanup_counts['logs']}")
            step_ok(f"Cleared challenge locks: {cleanup_counts['locks']}")
            step_ok(f"Cleared runtime tmp files: {cleanup_counts['tmp']}")

        output = _list_tunnel_processes()
        print()
        if output:
            print(output)
        else:
            print(yellow("No pinggy/ngrok/localtunnel processes found"))
        print()
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Process check failed: {str(e)}\n")
        return 1
