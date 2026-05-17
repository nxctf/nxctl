"""CLI command handlers for challenge lifecycle management."""

import logging
import os
import time
from nxctl.core.constants import PROTOCOL_TCP, EXPORT_PROVIDER_PINGGY, EXPORT_PROVIDER_LOCALTUNNEL
from nxctl.scripts.cli.base import (
    get_services,
    get_container_port,
    green,
    red,
    yellow,
    blue,
    bold,
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


def _stop_challenge_completely(name: str, challenge_service, runtime_service, export_manager):
    """Stop both exports and container for a challenge."""
    challenge = challenge_service.get_challenge(name)
    if challenge:
        # 1. Stop exports (kills PIDs)
        exports = export_manager.list_exports(name)
        for export in exports:
            try:
                export_manager.stop_export(name, export["provider"], challenge.service_port)
                logger.info(f"Stopped {export['provider']} export for {name}")
            except Exception as e:
                logger.error(f"Failed to stop export {export['provider']} for {name}: {e}")

        # 2. Stop container
        try:
            runtime_service.stop(name)
            logger.info(f"Stopped container for {name}")
        except Exception as e:
            logger.error(f"Failed to stop container for {name}: {e}")
    else:
        # Fallback if challenge not in DB but maybe runtime exists
        try:
            runtime_service.stop(name)
        except:
            pass


def cmd_up(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1

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
        _, challenge_service, runtime_service, export_manager = get_services()
        print(f"\n{blue('Stopping...')}")
        _stop_challenge_completely(args.name, challenge_service, runtime_service, export_manager)
        print(f"{green('✓')} Down complete\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Down failed: {str(e)}\n")
        return 1


def cmd_restart(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()

        # 1. Check Cooldown
        remaining = runtime_service.check_restart_cooldown(args.name)
        if remaining:
            print(f"\n{red('✗')} Restart denied: Cooldown active. Please wait {remaining}s.\n")
            return 1

        # 2. Determine what to restart
        restart_all = not (args.container or args.provider)
        do_container = restart_all or args.container
        do_provider = restart_all or args.provider

        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red('✗')} Challenge not found: {args.name}\n")
            return 1

        print(f"\n{blue('Restarting...')}")

        # Handle Provider Stop
        if do_provider:
            exports = export_manager.list_exports(args.name)
            for export in exports:
                export_manager.stop_export(args.name, export["provider"], challenge.service_port)
                print(f"{blue('  • Stopped export:')} {export['provider']}")

        # Handle Container Restart
        if do_container:
            runtime_service.stop(args.name)
            runtime_service.start(args.name)
            # Re-fetch challenge for updated data
            challenge = challenge_service.get_challenge(args.name)
            print(f"{green('  • Container restarted')}")

        # Re-start provider if needed
        if do_provider:
            provider, endpoint = _start_with_fallback(export_manager, args.name, challenge)
            print(f"{green('  • Export restarted via')} {provider}")
            print(f"    Endpoint: {endpoint}")

        # 3. Update last_restart time
        runtime_service.update_restart_time(args.name)

        print(f"\n{green('✓')} Restart complete\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Restart failed: {str(e)}\n")
        return 1


def cmd_status(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()

        watch_mode = getattr(args, "watch", False)

        while True:
            # 1. Handle auto-shutdown for expired runtimes
            import sqlite3
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

            print(f"{'-' * 160}")
            print(f"{'Challenge':30} | {'Port (L:C)':12} | {'Export':8} | {'Provider':12} | {'Endpoint':50} | {'PID':8} | {'Remaining':12}")
            print(f"{'-' * 160}")

            for challenge in challenges:
                runtime = runtime_service.status(challenge.name)
                exports = export_manager.list_exports(challenge.name, check_health=True)

                # Runtime indicators
                is_running = runtime.status == 'running'
                challenge_icon = green('✓') if is_running else red('✗')

                name_padding = " " * max(0, 28 - len(challenge.name))
                challenge_col = f"{challenge_icon} {challenge.name}{name_padding}"

                # Export indicators
                export_active = any(e['status'] == 'active' for e in exports)
                if export_active:
                    export_status_icon = f"  {green('✓')}     "
                elif exports:
                    export_status_icon = f"  {yellow('⚠')}     "
                else:
                    export_status_icon = f"  {red('✗')}     "

                # Port mapping
                container_port = get_container_port(config, challenge)
                port_mapping = f"{challenge.service_port}:{container_port}"
                port_col = f"{port_mapping:12}"

                # Provider, PID and Endpoint
                raw_provider = exports[0]["provider"] if exports else "-"
                raw_pid = str(exports[0]["pid"]) if exports and exports[0]["pid"] else "-"
                raw_endpoint = exports[0]["endpoint"] if exports else "-"

                # Coloring and truncation
                is_dead = exports and exports[0]['status'] == 'dead'

                if is_dead:
                    provider_col = red(f"{raw_provider:12}")
                    pid_col = red(f"{raw_pid:8}")
                    endpoint_label = red("[DEAD]") + f" {raw_endpoint}"
                else:
                    provider_col = f"{raw_provider:12}"
                    pid_col = f"{raw_pid:8}"
                    endpoint_label = raw_endpoint

                display_endpoint = endpoint_label
                if len(raw_endpoint) > 50:
                    display_endpoint = endpoint_label[:47] + "..."

                # Remaining time
                remaining_col = "-"
                if runtime.status == 'running' and runtime.expires_at:
                    from datetime import datetime
                    remaining = runtime.expires_at - datetime.now()
                    rem_seconds = remaining.total_seconds()
                    if rem_seconds > 0:
                        mins = int(rem_seconds // 60)
                        secs = int(rem_seconds % 60)
                        remaining_str = f"{mins}m {secs}s"
                        if mins < config.extend_threshold_minutes:
                            remaining_col = yellow(f"{remaining_str:12}")
                        else:
                            remaining_col = green(f"{remaining_str:12}")
                    else:
                        remaining_col = red(f"{'EXPIRED':12}")

                print(f"{challenge_col} | {port_col} | {export_status_icon} | {provider_col} | {display_endpoint:50} | {pid_col} | {remaining_col}")

            print(f"{'-' * 160}\n")

            if not watch_mode:
                break

            time.sleep(15)

        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Status failed: {str(e)}\n")
        return 1


def cmd_extend(args) -> int:
    try:
        _, _, runtime_service, _ = get_services()
        runtime = runtime_service.extend_time(args.name)

        from datetime import datetime
        remaining = runtime.expires_at - datetime.now()
        mins = int(remaining.total_seconds() // 60)
        secs = int(remaining.total_seconds() % 60)

        print(f"\n{green('✓')} Extended {args.name}")
        print(f"  New expiry: {runtime.expires_at.strftime('%H:%M:%S')}")
        print(f"  Time remaining: {mins}m {secs}s\n")
        return 0
    except Exception as e:
        print(f"\n{red('✗')} Extend failed: {str(e)}\n")
        return 1

def cmd_daemon(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        # Priority: CLI argument > Config file
        interval = getattr(args, "interval", None) or config.daemon_interval
        with_api = getattr(args, "with_api", False)

        print(f"\n{blue('[daemon]')} Starting CTF Orchestrator Daemon")
        print(f"{blue('[daemon]')} Interval: {interval}s")

        if with_api:
            import threading
            import uvicorn
            host = getattr(args, "host", "0.0.0.0")
            port = getattr(args, "port", 8000)

            def run_api():
                print(f"{blue('[api]')} Starting Web API on {host}:{port} (background)")
                uvicorn.run("src.api:app", host=host, port=port, log_level="warning")

            api_thread = threading.Thread(target=run_api, daemon=True)
            api_thread.start()

        print(f"{blue('[daemon]')} Monitoring challenges for auto-shutdown & auto-heal...\n")

        while True:
            try:
                # 1. Fetch data from DB
                import sqlite3
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
                        active_exports = export_manager.list_exports(name, check_health=False)
                        # After reconcile, if no active exports exist, it means the tunnel died
                        if not active_exports:
                            print(f"{blue('[daemon]')} Healing missing export for: {name}")
                            try:
                                challenge = challenge_service.get_challenge(name)
                                _start_with_fallback(export_manager, name, challenge)
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

        uvicorn.run("src.api:app", host=host, port=port, reload=False)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"\n{red('✗')} API failed: {str(e)}\n")
        return 1
