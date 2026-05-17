"""CLI command handlers for challenge management."""

import logging
from nxctl.core.git import GitRepository, GitError
from nxctl.scripts.challenge_service import ChallengeDiscoveryError
from nxctl.scripts.cli.base import (
    get_services,
    get_container_port,
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
    format_datetime,
    format_duration,
    panel,
    status_text,
    ttl_remaining,
)

logger = logging.getLogger(__name__)


def cmd_sync(args) -> int:
    try:
        config, challenge_service, _, _ = get_services()
        git_repo = GitRepository(
            repo_url=config.github_repo,
            cache_dir=config.cache_dir,
            branch=config.branch,
            token=config.access_token,
        )

        print(f"\n{blue('Syncing challenges...')}")
        challenges = challenge_service.sync_challenges(git_repo)
        print(f"{green(OK)} Synced {len(challenges)} challenges\n")
        for challenge in challenges:
            print(f"  {BULLET} {challenge.name} ({challenge.service_type}:{challenge.service_port})")
        print()
        return 0
    except GitError as e:
        print(f"\n{red(ERR)} Sync failed: {str(e)}\n")
        return 1
    except ChallengeDiscoveryError as e:
        print(f"\n{red(ERR)} Sync failed: {str(e)}\n")
        return 1
    except Exception as e:
        print(f"\n{red(ERR)} Sync failed: {str(e)}\n")
        return 1


def cmd_list(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        challenges = challenge_service.list_challenges()
        if not challenges:
            print(f"\n{yellow('No challenges found')}\n")
            return 0

        print(f"\n{bold('Challenges')}")
        print(f"{'-' * 100}")
        print(f"{'Name':28} {'Type':8} {'Port':8} {'Path'}")
        print(f"{'-' * 100}")
        for challenge in challenges:
            print(f"{challenge.name:28} {challenge.service_type:8} {str(challenge.service_port):8} {challenge.path}")
        print(f"{'-' * 100}\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} List failed: {str(e)}\n")
        return 1


def cmd_inspect(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"\n{red(ERR)} Challenge not found: {args.name}\n")
            return 1

        container_port = get_container_port(config, challenge)
        runtime = runtime_service.status(args.name)
        cooldown = runtime_service.check_restart_cooldown(args.name)
        exports = export_manager.list_exports(args.name, check_health=True)
        ttl_text, ttl_ok = ttl_remaining(runtime.expires_at)
        protocol = str(challenge.service_type or "-").upper()
        configured_provider = (
            runtime.tunnel_provider
            or getattr(config, "default_tunnel", "")
            or export_manager.default_providers_for(challenge.service_type)[0]
        )
        base_ip = str(getattr(config, "base_ip", "") or "").strip() or "Not configured"
        ngrok_status = green("Available") if export_manager.ngrok_available() else yellow("Unavailable")
        restart_cd = yellow(f"{format_duration(cooldown)} left") if cooldown else green("Ready")
        ttl_value = green(ttl_text) if ttl_ok and ttl_text != "-" else red("Expired") if ttl_text != "-" else "-"

        print()
        print(panel(
            f"Challenge: {challenge.name}",
            [
                ("Path", challenge.path),
                ("Type", protocol),
                ("Internal Port", container_port),
                ("Host Port", challenge.service_port),
                ("Enabled", green("Yes") if challenge.enabled else red("No")),
                ("Created", format_datetime(challenge.created_at)),
            ],
        ))
        print()
        print(panel(
            "Configuration",
            [
                ("Tunnel Provider", configured_provider or "-"),
                ("Base IP", base_ip),
                ("Ngrok", ngrok_status),
                ("Auto Export", green("Enabled")),
                ("Auto Heal", green("Enabled") if getattr(config, "auto_heal_exports", False) else red("Disabled")),
            ],
        ))
        print()
        print(panel(
            "Runtime",
            [
                ("Status", status_text(runtime.status)),
                ("Container", runtime.container_id or "-"),
                ("Started At", format_datetime(runtime.started_at)),
                ("Expires At", format_datetime(runtime.expires_at)),
                ("TTL Remaining", ttl_value),
                ("Restart CD", restart_cd),
            ],
        ))
        print()
        print(box("Active Exports", exports_table(exports, detailed=True), width=116))
        print()
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Inspect failed: {str(e)}\n")
        return 1


def cmd_add(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        challenge = challenge_service.add_challenge(args.name, args.path, args.port, args.type)
        print(f"\n{green(OK)} Added challenge: {challenge.name}\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Add failed: {str(e)}\n")
        return 1


def cmd_remove(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        if not challenge_service.remove_challenge(args.name):
            print(f"\n{red(ERR)} Challenge not found: {args.name}\n")
            return 1
        print(f"\n{green(OK)} Removed challenge: {args.name}\n")
        return 0
    except Exception as e:
        print(f"\n{red(ERR)} Remove failed: {str(e)}\n")
        return 1
