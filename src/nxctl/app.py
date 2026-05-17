#!/usr/bin/env python3
"""NXCTL command-line interface."""

import logging
import sys
import argparse
import os
from pathlib import Path

# Auto-detect project root for both root and src layouts.
PACKAGE_DIR = Path(__file__).resolve().parent
if PACKAGE_DIR.parent.name == "src":
    PROJECT_ROOT = str(PACKAGE_DIR.parent.parent)
    SRC_ROOT = str(PACKAGE_DIR.parent)
else:
    PROJECT_ROOT = str(PACKAGE_DIR.parent)
    SRC_ROOT = PROJECT_ROOT
os.chdir(PROJECT_ROOT)
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

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
    level=logging.WARNING,
    format="%(message)s"
)
logger = logging.getLogger(__name__)

# Import command handlers from modular CLI package
from nxctl.scripts.cli.challenges import (
    cmd_sync,
    cmd_list,
    cmd_inspect,
    cmd_add,
    cmd_remove,
)
from nxctl.scripts.cli.lifecycle import (
    cmd_up,
    cmd_down,
    cmd_restart,
    cmd_status,
    cmd_extend,
    cmd_daemon,
    cmd_api,
)
from nxctl.scripts.cli.exports import (
    cmd_export,
    cmd_unexport,
    cmd_exports,
    cmd_test,
)


def add_debug_flag(parser: argparse.ArgumentParser, *, default=False) -> None:
    """Add a debug/verbose flag that can be used before or after commands."""
    parser.add_argument(
        "-v",
        "--verbose",
        "--debug",
        dest="debug",
        action="store_true",
        default=default,
        help="Show raw debug logs",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build flat command parser."""
    parser = argparse.ArgumentParser(
        description="NXCTL challenge orchestration",
        prog="nxctl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nxctl sync                      Sync all challenges from repo
  nxctl list                      List all challenges
  nxctl up web/sqli               Build + start + auto-export
  nxctl down web/sqli             Stop container + exports
  nxctl status                    Show running challenges + exports
  nxctl export ngrok web/sqli     Manual ngrok tunnel
  nxctl unexport web/sqli         Stop all exports
        """.strip()
    )
    add_debug_flag(parser, default=False)

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ======== DATA MANAGEMENT ========
    sync_cmd = subparsers.add_parser("sync", help="Sync challenges from repository")
    add_debug_flag(sync_cmd, default=argparse.SUPPRESS)
    sync_cmd.set_defaults(func=cmd_sync)

    list_cmd = subparsers.add_parser("list", help="List all challenges")
    add_debug_flag(list_cmd, default=argparse.SUPPRESS)
    list_cmd.add_argument("-a", "--all", action="store_true", help="Show full details")
    list_cmd.set_defaults(func=cmd_list)

    inspect_cmd = subparsers.add_parser("inspect", help="Show challenge details")
    add_debug_flag(inspect_cmd, default=argparse.SUPPRESS)
    inspect_cmd.add_argument("name", help="Challenge name")
    inspect_cmd.set_defaults(func=cmd_inspect)

    add_cmd = subparsers.add_parser("add", help="Add challenge manually")
    add_debug_flag(add_cmd, default=argparse.SUPPRESS)
    add_cmd.add_argument("name", help="Challenge name (e.g., web/sqli)")
    add_cmd.add_argument("path", help="Path in repo (e.g., web/sqli)")
    add_cmd.add_argument("port", type=int, help="Service port")
    add_cmd.add_argument("--type", choices=["http", "tcp"], default="http", help="Service type")
    add_cmd.set_defaults(func=cmd_add)

    remove_cmd = subparsers.add_parser("remove", help="Remove challenge")
    add_debug_flag(remove_cmd, default=argparse.SUPPRESS)
    remove_cmd.add_argument("name", help="Challenge name")
    remove_cmd.set_defaults(func=cmd_remove)

    # ======== LIFECYCLE ========
    up_cmd = subparsers.add_parser("up", help="Build + start + auto-export")
    add_debug_flag(up_cmd, default=argparse.SUPPRESS)
    up_cmd.add_argument("name", nargs="?", help="Challenge name")
    up_cmd.add_argument("--all", action="store_true", help="Start all enabled challenges")
    up_cmd.set_defaults(func=cmd_up)

    down_cmd = subparsers.add_parser("down", help="Stop container + exports")
    add_debug_flag(down_cmd, default=argparse.SUPPRESS)
    down_cmd.add_argument("name", nargs="?", help="Challenge name")
    down_cmd.add_argument("--all", action="store_true", help="Stop all running challenges and tunnel processes")
    down_cmd.set_defaults(func=cmd_down)

    restart_cmd = subparsers.add_parser("restart", help="Restart (down + up)")
    add_debug_flag(restart_cmd, default=argparse.SUPPRESS)
    restart_cmd.add_argument("name", help="Challenge name")
    restart_cmd.add_argument("--container", action="store_true", help="Restart only the docker container")
    restart_cmd.add_argument("--provider", action="store_true", help="Restart only the tunnel provider")
    restart_cmd.set_defaults(func=cmd_restart)

    status_cmd = subparsers.add_parser("status", help="Show running challenges + exports")
    add_debug_flag(status_cmd, default=argparse.SUPPRESS)
    status_cmd.add_argument("name", nargs="?", help="Optional challenge name filter")
    status_cmd.add_argument("-w", "--watch", action="store_true", help="Watch status in real-time (every 15s)")
    status_cmd.set_defaults(func=cmd_status)

    extend_cmd = subparsers.add_parser("extend", help="Extend challenge runtime")
    add_debug_flag(extend_cmd, default=argparse.SUPPRESS)
    extend_cmd.add_argument("name", help="Challenge name")
    extend_cmd.set_defaults(func=cmd_extend)

    daemon_cmd = subparsers.add_parser("daemon", help="Run background monitor daemon")
    add_debug_flag(daemon_cmd, default=argparse.SUPPRESS)
    daemon_cmd.add_argument("--interval", type=int, help="Check interval in seconds")
    daemon_cmd.add_argument("--with-api", action="store_true", help="Also start the Web API server")
    daemon_cmd.add_argument("--host", default="0.0.0.0", help="API listen host")
    daemon_cmd.add_argument("--port", type=int, default=8000, help="API listen port")
    daemon_cmd.set_defaults(func=cmd_daemon)

    api_cmd = subparsers.add_parser("api", help="Run Web API server")
    add_debug_flag(api_cmd, default=argparse.SUPPRESS)
    api_cmd.add_argument("--host", default="0.0.0.0", help="Listen host")
    api_cmd.add_argument("--port", type=int, default=8000, help="Listen port")
    api_cmd.set_defaults(func=cmd_api)

    # ======== EXPORT MANAGEMENT ========
    export_cmd = subparsers.add_parser("export", help="Manual tunnel, or auto-pick if provider omitted")
    add_debug_flag(export_cmd, default=argparse.SUPPRESS)
    export_cmd.add_argument("target", help="Challenge name, or provider name if followed by a challenge name")
    export_cmd.add_argument("name", nargs="?", help="Challenge name when provider is specified")
    export_cmd.set_defaults(func=cmd_export)

    unexport_cmd = subparsers.add_parser("unexport", help="Stop all exports for a challenge")
    add_debug_flag(unexport_cmd, default=argparse.SUPPRESS)
    unexport_cmd.add_argument("name", help="Challenge name")
    unexport_cmd.set_defaults(func=cmd_unexport)

    exports_cmd = subparsers.add_parser("exports", help="List active exports/tunnels")
    add_debug_flag(exports_cmd, default=argparse.SUPPRESS)
    exports_cmd.add_argument("--all", action="store_true", help="Show all history")
    exports_cmd.set_defaults(func=cmd_exports)

    test_cmd = subparsers.add_parser("test", help="Actively test tunnel endpoints")
    add_debug_flag(test_cmd, default=argparse.SUPPRESS)
    test_cmd.add_argument("name", nargs="?", help="Optional challenge name filter")
    test_cmd.set_defaults(func=cmd_test)

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "debug", False) or os.getenv("NXCTL_DEBUG"):
        logging.getLogger().setLevel(logging.INFO)

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
        print("\nCancelled by user")
        return 130
    except Exception as e:
        print(f"\nError: {str(e)}")
        logger.exception("Unhandled exception:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
