"""CLI command handlers."""

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
)

__all__ = [
    "cmd_challenge_sync",
    "cmd_challenge_list",
    "cmd_challenge_inspect",
    "cmd_challenge_add",
    "cmd_challenge_remove",
    "cmd_challenge_enable",
    "cmd_challenge_disable",
    "cmd_runtime_build",
    "cmd_runtime_start",
    "cmd_runtime_stop",
    "cmd_runtime_status",
]
