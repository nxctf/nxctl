#!/usr/bin/env python3
"""CTF Challenge Orchestration Engine - CLI Entry Point."""

import logging
import sys
import argparse
import os
from pathlib import Path

# Auto-load .env into process environment so config substitution works
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

env_path = Path(".env")
if env_path.exists():
    try:
        if load_dotenv:
            load_dotenv(dotenv_path=str(env_path))
        else:
            # minimal loader: KEY=VALUE lines
            with open(env_path, "r") as ef:
                for line in ef:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        os.environ.setdefault(k, v)
    except Exception:
        pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Import CLI commands
from src.cli.challenge_commands import (
    cmd_challenge_sync,
    cmd_challenge_list,
    cmd_challenge_inspect,
    cmd_challenge_add,
    cmd_challenge_remove,
    cmd_challenge_enable,
    cmd_challenge_disable,
)
from src.cli.runtime_commands import (
    cmd_runtime_build,
    cmd_runtime_start,
    cmd_runtime_stop,
    cmd_runtime_status,
    cmd_runtime_force_stop,
)
from src.cli.export_commands import (
    cmd_export,
    cmd_export_ngrok,
    cmd_export_localtunnel,
    cmd_export_list,
    cmd_export_stop,
    cmd_export_prune,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CTF Challenge Orchestration Engine",
        prog="ctf-orch",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Challenge commands
    challenge_parser = subparsers.add_parser("challenge", help="Manage challenges")
    challenge_sub = challenge_parser.add_subparsers(dest="subcommand")

    # challenge sync
    sync_cmd = challenge_sub.add_parser("sync", help="Sync challenges from repository")
    sync_cmd.set_defaults(func=cmd_challenge_sync)

    # challenge list
    list_cmd = challenge_sub.add_parser("list", help="List all challenges")
    list_cmd.set_defaults(func=cmd_challenge_list)

    # challenge inspect
    inspect_cmd = challenge_sub.add_parser("inspect", help="Inspect challenge details")
    inspect_cmd.add_argument("name", help="Challenge name")
    inspect_cmd.set_defaults(func=cmd_challenge_inspect)

    # challenge add
    add_cmd = challenge_sub.add_parser("add", help="Add a challenge manually")
    add_cmd.add_argument("name", help="Challenge name (e.g., web/sqli-basic)")
    add_cmd.add_argument("path", help="Challenge path in repo (e.g., web/sqli-basic)")
    add_cmd.add_argument("port", type=int, help="Service port (e.g., 8080)")
    add_cmd.add_argument("--type", choices=["http", "tcp"], default="http", help="Service type (default: http)")
    add_cmd.set_defaults(func=cmd_challenge_add)

    # challenge remove
    remove_cmd = challenge_sub.add_parser("remove", help="Remove a challenge")
    remove_cmd.add_argument("name", help="Challenge name")
    remove_cmd.set_defaults(func=cmd_challenge_remove)

    # challenge enable
    enable_cmd = challenge_sub.add_parser("enable", help="Enable a challenge")
    enable_cmd.add_argument("name", help="Challenge name")
    enable_cmd.set_defaults(func=cmd_challenge_enable)

    # challenge disable
    disable_cmd = challenge_sub.add_parser("disable", help="Disable a challenge")
    disable_cmd.add_argument("name", help="Challenge name")
    disable_cmd.set_defaults(func=cmd_challenge_disable)

    # Runtime commands
    runtime_parser = subparsers.add_parser("runtime", help="Manage challenge runtimes")
    runtime_sub = runtime_parser.add_subparsers(dest="subcommand")

    # runtime build
    build_cmd = runtime_sub.add_parser("build", help="Build Docker image for a challenge")
    build_cmd.add_argument("name", help="Challenge name")
    build_cmd.set_defaults(func=cmd_runtime_build)

    # runtime start
    start_cmd = runtime_sub.add_parser("start", help="Start a challenge runtime")
    start_cmd.add_argument("name", help="Challenge name")
    start_cmd.set_defaults(func=cmd_runtime_start)

    # runtime stop
    stop_cmd = runtime_sub.add_parser("stop", help="Stop a challenge runtime")
    stop_cmd.add_argument("name", help="Challenge name")
    stop_cmd.set_defaults(func=cmd_runtime_stop)

    # runtime status
    status_cmd = runtime_sub.add_parser("status", help="Show runtime status")
    status_cmd.add_argument("name", nargs="?", default=None, help="Challenge name (optional)")
    status_cmd.set_defaults(func=cmd_runtime_status)

    # runtime force-stop
    force_stop_cmd = runtime_sub.add_parser("force-stop", help="Force stop runtime containers")
    force_stop_cmd.add_argument("name", nargs="?", default=None, help="Challenge name (optional when --all used)")
    force_stop_cmd.add_argument("--all", action="store_true", help="Force stop all known challenge runtimes")
    force_stop_cmd.set_defaults(func=cmd_runtime_force_stop)

    # export runtime to public tunnel (subcommands)
    export_parser = subparsers.add_parser("export", help="Export running challenge to public tunnel")
    export_sub = export_parser.add_subparsers(dest="subcommand")

    # export ngrok
    export_ngrok = export_sub.add_parser("ngrok", help="Export via ngrok")
    export_ngrok.add_argument("name", help="Challenge name (e.g., chall/simplee)")
    export_ngrok.set_defaults(func=cmd_export_ngrok)

    # export localtunnel
    export_lt = export_sub.add_parser("localtunnel", help="Export via localtunnel")
    export_lt.add_argument("name", help="Challenge name (e.g., chall/simplee)")
    export_lt.set_defaults(func=cmd_export_localtunnel)

    # export list
    export_list = export_sub.add_parser("list", help="List active exports/tunnels")
    export_list.add_argument("name", nargs="?", help="Optional challenge name to filter")
    export_list.add_argument("--all", action="store_true", help="Show all history rows (including duplicates)")
    export_list.set_defaults(func=cmd_export_list)

    # export stop
    export_stop = export_sub.add_parser("stop", help="Stop export/tunnel for a challenge")
    export_stop.add_argument("name", help="Challenge name (e.g., chall/simplee)")
    export_stop.add_argument("provider", nargs="?", choices=["ngrok", "localtunnel"], help="Optional provider to stop (ngrok|localtunnel). If omitted, stop all providers for the challenge.")
    export_stop.set_defaults(func=cmd_export_stop)

    # export prune
    export_prune = export_sub.add_parser("prune", help="Delete non-active export records from DB")
    export_prune.add_argument("provider", nargs="?", choices=["ngrok", "localtunnel"], help="Optional provider filter (positional)")
    export_prune.set_defaults(func=cmd_export_prune)

    # Parse arguments
    args = parser.parse_args()

    # Handle no command
    if not args.command:
        parser.print_help()
        return 0

    # Handle no subcommand for challenge
    if args.command == "challenge" and not args.subcommand:
        challenge_parser.print_help()
        return 0

    # Execute command
    if hasattr(args, "func"):
        try:
            return args.func(args)
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            return 1
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
