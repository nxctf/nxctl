#!/usr/bin/env python3
"""CTF Challenge Orchestration Engine - CLI Entry Point."""

import logging
import sys
import argparse

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
    sys.exit(main())
