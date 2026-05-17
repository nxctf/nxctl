"""CLI command handlers for challenge lifecycle management."""

import logging
import os
import time
from types import SimpleNamespace
from nxctl.core.constants import PROTOCOL_TCP, EXPORT_PROVIDER_PINGGY, EXPORT_PROVIDER_LOCALTUNNEL
from nxctl.scripts.cli.base import (
    get_services,
    green,
    red,
    yellow,
    blue,
    bold,
)
from nxctl.scripts.cli.render import (
    BULLET,
    ERR,
    OK,
    box,
    exports_table,
    format_error,
    green as rgreen,
    red as rred,
    spinner,
    status_text,
    step_ok,
    step_warn,
    table,
    ttl_remaining,
)

logger = logging.getLogger(__name__)


def _provider_priority(service_type: str) -> list[str]:
    if service_type == PROTOCOL_TCP:
        return [EXPORT_PROVIDER_PINGGY]
    return [EXPORT_PROVIDER_LOCALTUNNEL]


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


def _port_summary(ports) -> str:
    if not ports:
        return "-"
    return ", ".join(f"{port.host_port}:{port.internal_port}/{port.service_type}" for port in ports)


def _start_available_exports(export_manager, challenge_name: str, challenge, ports=None) -> tuple[list[dict], list[dict]]:
    """Start every auto-discovered export while preserving default tunnel selection."""
    all_exports: list[dict] = []
    all_failures: list[dict] = []
    export_ports = ports or [SimpleNamespace(
        host_port=challenge.service_port,
        service_port=challenge.service_port,
        service_type=challenge.service_type,
    )]

    for port in export_ports:
        port_challenge = SimpleNamespace(
            service_port=int(getattr(port, "host_port", getattr(port, "service_port", challenge.service_port))),
            service_type=str(getattr(port, "service_type", challenge.service_type)),
        )
        exports, failures = export_manager.start_available_exports(
            challenge_name,
            port_challenge,
            default_providers=_provider_priority(port_challenge.service_type),
        )
        all_exports.extend(exports)
        all_failures.extend(failures)

    return all_exports, all_failures


def _stop_challenge_completely(name: str, challenge_service, runtime_service, export_manager):
    """Stop both exports and container for a challenge."""
    challenge = challenge_service.get_challenge(name)
    if challenge:
        # Mark stopped first so the daemon cannot auto-heal tunnels during down.
        try:
            runtime_service.mark_stopped(name)
        except Exception as e:
            logger.warning(f"Failed to pre-mark runtime stopped for {name}: {e}")

        # 1. Stop container
        try:
            runtime_service.stop(name)
            logger.info(f"Stopped container for {name}")
        except Exception as e:
            logger.error(f"Failed to stop container for {name}: {e}")

        # 2. Stop exports after runtime is no longer considered running.
        for export in export_manager.stop_all_exports(name):
            if export.get("error"):
                logger.error(f"Failed to stop export {export['provider']} for {name}: {export['error']}")
            else:
                logger.info(f"Stopped {export['provider']} export for {name}")

        # One more pass catches tunnels created by an overlapping daemon tick.
        for export in export_manager.stop_all_exports(name):
            if export.get("error"):
                logger.error(f"Failed to stop late export {export['provider']} for {name}: {export['error']}")
    else:
        # Fallback if challenge not in DB but maybe runtime exists
        try:
            runtime_service.stop(name)
        except Exception:
            pass


def cmd_up(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        print(f"\n{bold(f'Starting challenge: {args.name}')}\n")

        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red(ERR)} Challenge not found: {args.name}\n")
            return 1
        step_ok("Loaded challenge config")

        with spinner("Starting Docker container"):
            runtime_service.start(args.name)
        challenge = challenge_service.get_challenge(args.name) or challenge
        ports = challenge_service.list_challenge_ports(args.name)
        runtime = runtime_service.status(args.name)
        step_ok(f"Allocated host ports: {_port_summary(ports)}")
        step_ok("Docker container started")
        ttl_text, _ = ttl_remaining(runtime.expires_at)
        step_ok(f"TTL registered: {ttl_text}")

        with spinner("Creating exports"):
            exports, failures = _start_available_exports(export_manager, args.name, challenge, ports)

        print()
        print(box("Exports", exports_table(exports), width=116))
        for failure in failures:
            step_warn(f"{failure['provider']} export failed: {format_error(failure['error'])}")

        print(f"\n{green(OK)} Challenge is running.")
        print(f"Expires in: {ttl_text}\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Up failed: {str(e)}\n")
        return 1


def cmd_down(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = get_services()

        if getattr(args, "all", False):
            print(f"\n{blue('Stopping all challenges...')}")
            stopped_count = 0

            for challenge in challenge_service.list_challenges():
                runtime = runtime_service.status(challenge.name)
                exports = export_manager.list_exports(challenge.name, check_health=False)
                if runtime.status != "running" and not exports:
                    continue

                print(f"{blue(f'  {BULLET}')} {challenge.name}")
                _stop_challenge_completely(
                    challenge.name,
                    challenge_service,
                    runtime_service,
                    export_manager,
                )
                stopped_count += 1

            killed = export_manager.kill_all_tunnel_processes()
            export_manager.mark_all_exports_inactive()

            print(f"{green(OK)} Down complete")
            print(f"  Challenges handled: {stopped_count}")
            print(f"  Tunnel processes killed: {killed}\n")
            return 0

        if not args.name:
            print(f"\n{red(ERR)} Please provide a challenge name or use --all\n")
            return 1

        print(f"\n{blue('Stopping...')}")
        _stop_challenge_completely(args.name, challenge_service, runtime_service, export_manager)
        print(f"{green(OK)} Down complete\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Down failed: {str(e)}\n")
        return 1


def cmd_restart(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = get_services()

        # 1. Check Cooldown
        remaining = runtime_service.check_restart_cooldown(args.name)
        if remaining:
            print(f"\n{red(ERR)} Restart denied: Cooldown active. Please wait {remaining}s.\n")
            return 1

        # 2. Determine what to restart
        restart_all = not (args.container or args.provider)
        do_container = restart_all or args.container
        do_provider = restart_all or args.provider

        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red(ERR)} Challenge not found: {args.name}\n")
            return 1

        print(f"\n{blue('Restarting...')}")

        # Handle Provider Stop
        if do_provider:
            for export in export_manager.stop_all_exports(args.name):
                print(f"{blue(f'  {BULLET} Stopped export:')} {export['provider']}")

        # Handle Container Restart
        if do_container:
            runtime_service.stop(args.name)
            runtime_service.start(args.name)
            # Re-fetch challenge for updated data
            challenge = challenge_service.get_challenge(args.name)
            print(f"{green(f'  {BULLET} Container restarted')}")

        # Re-start provider if needed
        if do_provider:
            ports = challenge_service.list_challenge_ports(args.name)
            exports, failures = _start_available_exports(export_manager, args.name, challenge, ports)
            for export in exports:
                print(f"{green(f'  {BULLET} Export restarted via')} {export['provider']} ({export['type']})")
                print(f"    URL: {export['url']}")
            for failure in failures:
                print(f"{yellow(f'  {BULLET} Export failed:')} {failure['provider']} - {format_error(failure['error'])}")

        # 3. Update last_restart time
        runtime_service.update_restart_time(args.name)

        print(f"\n{green(OK)} Restart complete\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Restart failed: {str(e)}\n")
        return 1


def cmd_status(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()

        watch_mode = getattr(args, "watch", False)

        while True:
            # 1. Handle auto-shutdown for expired runtimes
            from nxctl.core.db import get_db_connection, close_db_connection
            conn = get_db_connection(config.db_file)
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT c.name
                    FROM runtime_instances r
                    JOIN challenges c ON r.challenge_id = c.id
                    WHERE r.status = 'running'
                    AND r.expires_at IS NOT NULL
                    AND r.expires_at < datetime('now', 'localtime')
                """)
                expired = [row["name"] for row in cursor.fetchall()]
            finally:
                close_db_connection(conn)

            for name in expired:
                logger.info(f"Auto-stopping expired challenge: {name}")
                _stop_challenge_completely(name, challenge_service, runtime_service, export_manager)

            # 2. Reconcile exports (mark dead PIDs)
            export_manager.reconcile_exports()

            # 3. Get data for display
            challenges = [challenge_service.get_challenge(args.name)] if args.name else challenge_service.list_challenges()
            challenges = [challenge for challenge in challenges if challenge]

            if not challenges:
                if not watch_mode:
                    print(f"\n{yellow('No challenges found')}\n")
                    return 0

            if watch_mode:
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"\n{bold('Status (Watching every 15s - Ctrl+C to stop)')}")
            else:
                print(f"\n{bold('Status')}")

            status_rows = []

            for challenge in challenges:
                runtime = runtime_service.status(challenge.name)
                exports = export_manager.list_exports(challenge.name, check_health=True)
                ports = challenge_service.list_challenge_ports(challenge.name)
                port_mapping = _port_summary(ports)
                ttl_text, ttl_ok = ttl_remaining(runtime.expires_at)
                ttl_col = rgreen(ttl_text) if runtime.status == "running" and ttl_ok else rred("Expired") if runtime.status == "running" else "-"
                challenge_col = f"{rgreen(OK) if runtime.status == 'running' else rred(ERR)} {challenge.name}"

                export_rows = exports or [{
                    "provider": "-",
                    "type": "-",
                    "pid": None,
                    "endpoint": "-",
                    "status": "-"
                }]

                for index, export in enumerate(export_rows):
                    status_rows.append([
                        challenge_col if index == 0 else "",
                        status_text(runtime.status) if index == 0 else "",
                        port_mapping if index == 0 else "",
                        ttl_col if index == 0 else "",
                        export.get("provider") or "-",
                        export.get("type") or "-",
                        status_text(export.get("status")),
                        export.get("pid") or "-",
                        export.get("url") or export.get("endpoint") or "-",
                    ])

            if status_rows:
                print(table(
                    ["Challenge", "Runtime", "Port", "TTL", "Provider", "Type", "Export", "PID", "URL"],
                    status_rows,
                    [28, 10, 26, 12, 14, 8, 10, 8, 58],
                ))
            print()

            if not watch_mode:
                break

            time.sleep(15)

        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Status failed: {str(e)}\n")
        return 1


def cmd_extend(args) -> int:
    try:
        _, _, runtime_service, _ = get_services()
        runtime = runtime_service.extend_time(args.name)

        from datetime import datetime
        remaining = runtime.expires_at - datetime.now()
        mins = int(remaining.total_seconds() // 60)
        secs = int(remaining.total_seconds() % 60)

        print(f"\n{green(OK)} Extended {args.name}")
        print(f"  New expiry: {runtime.expires_at.strftime('%H:%M:%S')}")
        print(f"  Time remaining: {mins}m {secs}s\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Extend failed: {str(e)}\n")
        return 1

def cmd_daemon(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        # Priority: CLI argument > Config file
        interval = getattr(args, "interval", None) or config.daemon_interval
        with_api = getattr(args, "with_api", False)

        print(f"\n{blue('[daemon]')} Starting NXCTL Daemon")
        print(f"{blue('[daemon]')} Interval: {interval}s")

        if with_api:
            import threading
            import uvicorn
            host = getattr(args, "host", "0.0.0.0")
            port = getattr(args, "port", 8000)

            def run_api():
                print(f"{blue('[api]')} Starting Web API on {host}:{port} (background)")
                uvicorn.run("nxctl.api:app", host=host, port=port, log_level="warning")

            api_thread = threading.Thread(target=run_api, daemon=True)
            api_thread.start()

        print(f"{blue('[daemon]')} Monitoring challenges for auto-shutdown & auto-heal...\n")

        while True:
            try:
                # 1. Fetch data from DB
                from nxctl.core.db import get_db_connection, close_db_connection
                conn = get_db_connection(config.db_file)
                cursor = conn.cursor()
                try:
                    # Get expired runtimes
                    cursor.execute("""
                        SELECT c.name
                        FROM runtime_instances r
                        JOIN challenges c ON r.challenge_id = c.id
                        WHERE r.status = 'running'
                        AND r.expires_at IS NOT NULL
                        AND r.expires_at < datetime('now', 'localtime')
                    """)
                    expired = [row["name"] for row in cursor.fetchall()]

                    # Get all running runtimes for auto-heal
                    cursor.execute("""
                        SELECT c.name
                        FROM runtime_instances r
                        JOIN challenges c ON r.challenge_id = c.id
                        WHERE r.status = 'running'
                    """)
                    running_names = [row["name"] for row in cursor.fetchall()]
                finally:
                    close_db_connection(conn)

                # 2. Handle auto-shutdown for expired runtimes
                for name in expired:
                    print(f"{yellow('[daemon]')} Auto-stopping expired challenge: {name}")
                    _stop_challenge_completely(name, challenge_service, runtime_service, export_manager)
                    if name in running_names:
                        running_names.remove(name)

                # 3. Reconcile exports (mark dead PIDs as 'dead')
                export_manager.reconcile_exports()

                # 4. Auto-heal missing exports for running challenges
                if config.auto_heal_exports:
                    for name in running_names:
                        try:
                            challenge = challenge_service.get_challenge(name)
                            if runtime_service.status(name).status != "running":
                                continue
                            ports = challenge_service.list_challenge_ports(name)
                            _start_available_exports(export_manager, name, challenge, ports)
                        except Exception as heal_err:
                            print(f"{red('[daemon]')} Heal failed for {name}: {heal_err}")

            except Exception as e:
                print(f"{red('[daemon] Error:')} {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{yellow('[daemon]')} Shutting down daemon...")
        return 0
    except Exception as e:
        print(f"\n{red('[daemon]')} Fatal error: {str(e)}\n")
        return 1

def cmd_api(args) -> int:
    try:
        import uvicorn
        host = getattr(args, "host", "0.0.0.0")
        port = getattr(args, "port", 8000)

        print(f"\n{blue('[api]')} Starting NXCTL Web API on {host}:{port}")
        print(f"{blue('[api]')} Swagger UI: http://{host}:{port}/docs")

        uvicorn.run("nxctl.api:app", host=host, port=port, reload=False)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} API failed: {str(e)}\n")
        return 1
