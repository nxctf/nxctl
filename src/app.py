#!/usr/bin/env python3
"""CTF Challenge Orchestration Engine - Simplified Flat CLI."""

import logging
import sys
import argparse
import os
from pathlib import Path

# Auto-detect project root (one level up from src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Auto-load .env
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
    format="%(message)s"
)
logger = logging.getLogger(__name__)

# Import command handlers from modular CLI package
from src.scripts.cli.challenges import (
    cmd_sync,
    cmd_list,
    cmd_inspect,
    cmd_add,
    cmd_remove,
)
from src.scripts.cli.lifecycle import (
    cmd_up,
    cmd_down,
    cmd_restart,
    cmd_status,
    cmd_extend,
    cmd_daemon,
)
from src.scripts.cli.exports import (
    cmd_export,
    cmd_unexport,
    cmd_exports,
)


def build_parser() -> argparse.ArgumentParser:
    """Build flat command parser."""
    parser = argparse.ArgumentParser(
        description="CTF Challenge Orchestration - Simplified",
        prog="ctf-orch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ctf-orch sync                      Sync all challenges from repo
  ctf-orch list                      List all challenges
  ctf-orch up web/sqli               Build + start + auto-export
  ctf-orch down web/sqli             Stop container + exports
  ctf-orch status                    Show running challenges + exports
  ctf-orch export ngrok web/sqli     Manual ngrok tunnel
  ctf-orch unexport web/sqli         Stop all exports
        """.strip()
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ======== DATA MANAGEMENT ========
    sync_cmd = subparsers.add_parser("sync", help="Sync challenges from repository")
    sync_cmd.set_defaults(func=cmd_sync)

    list_cmd = subparsers.add_parser("list", help="List all challenges")
    list_cmd.add_argument("-a", "--all", action="store_true", help="Show full details")
    list_cmd.set_defaults(func=cmd_list)

    inspect_cmd = subparsers.add_parser("inspect", help="Show challenge details")
    inspect_cmd.add_argument("name", help="Challenge name")
    inspect_cmd.set_defaults(func=cmd_inspect)

    add_cmd = subparsers.add_parser("add", help="Add challenge manually")
    add_cmd.add_argument("name", help="Challenge name (e.g., web/sqli)")
    add_cmd.add_argument("path", help="Path in repo (e.g., web/sqli)")
    add_cmd.add_argument("port", type=int, help="Service port")
    add_cmd.add_argument("--type", choices=["http", "tcp"], default="http", help="Service type")
    add_cmd.set_defaults(func=cmd_add)

    remove_cmd = subparsers.add_parser("remove", help="Remove challenge")
    remove_cmd.add_argument("name", help="Challenge name")
    remove_cmd.set_defaults(func=cmd_remove)

    # ======== LIFECYCLE ========
    up_cmd = subparsers.add_parser("up", help="Build + start + auto-export")
    up_cmd.add_argument("name", help="Challenge name")
    up_cmd.set_defaults(func=cmd_up)

    down_cmd = subparsers.add_parser("down", help="Stop container + exports")
    down_cmd.add_argument("name", help="Challenge name")
    down_cmd.set_defaults(func=cmd_down)

    restart_cmd = subparsers.add_parser("restart", help="Restart (down + up)")
    restart_cmd.add_argument("name", help="Challenge name")
    restart_cmd.set_defaults(func=cmd_restart)

    status_cmd = subparsers.add_parser("status", help="Show running challenges + exports")
    status_cmd.add_argument("name", nargs="?", help="Optional challenge name filter")
    status_cmd.add_argument("-w", "--watch", action="store_true", help="Watch status in real-time (every 15s)")
    status_cmd.set_defaults(func=cmd_status)

    extend_cmd = subparsers.add_parser("extend", help="Extend challenge runtime")
    extend_cmd.add_argument("name", help="Challenge name")
    extend_cmd.set_defaults(func=cmd_extend)

    daemon_cmd = subparsers.add_parser("daemon", help="Run background monitor daemon")
    daemon_cmd.add_argument("--interval", type=int, help="Check interval in seconds")
    daemon_cmd.set_defaults(func=cmd_daemon)

    # ======== EXPORT MANAGEMENT ========
    export_cmd = subparsers.add_parser("export", help="Manual tunnel, or auto-pick if provider omitted")
    export_cmd.add_argument("target", help="Challenge name, or provider name if followed by a challenge name")
    export_cmd.add_argument("name", nargs="?", help="Challenge name when provider is specified")
    export_cmd.set_defaults(func=cmd_export)

    unexport_cmd = subparsers.add_parser("unexport", help="Stop all exports for a challenge")
    unexport_cmd.add_argument("name", help="Challenge name")
    unexport_cmd.set_defaults(func=cmd_unexport)

    exports_cmd = subparsers.add_parser("exports", help="List active exports/tunnels")
    exports_cmd.add_argument("--all", action="store_true", help="Show all history")
    exports_cmd.set_defaults(func=cmd_exports)

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if hasattr(args, "func"):
            return args.func(args)
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        print("\n✗ Cancelled by user")
        return 130
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        logger.exception("Unhandled exception:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
