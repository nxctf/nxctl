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
    bold,
)
from nxctl.scripts.cli.render import (
    ERR,
    OK,
    ProgressReporter,
    box,
    exports_table,
    format_datetime,
    format_duration,
    panel,
    status_text,
    table,
    ttl_remaining,
)

logger = logging.getLogger(__name__)


def _ports_text(challenge_service, challenge) -> str:
    ports = challenge_service.list_challenge_ports(challenge.name)
    if ports:
        return ", ".join(f"{p.host_port}:{p.internal_port}/{p.service_type}" for p in ports)
    return f"{challenge.service_port}/{challenge.service_type}"


def _key_text(config, challenge) -> str:
    if not challenge.access_key_hash:
        return "No"

    key_source = str(challenge.access_key_source or "").strip()
    if not key_source:
        return "(unavailable)"

    key_path = (config.chall_dir / key_source).resolve()
    try:
        return key_path.read_text(encoding="utf-8").strip() or "(empty)"
    except Exception:
        return "(unavailable)"


def cmd_sync(args) -> int:
    try:
        config, challenge_service, _, _ = get_services()
        git_repo = GitRepository(
            repo_url=config.github_repo,
            cache_dir=config.chall_dir,
            branch=config.branch,
            token=config.access_token,
        )

        print(f"{bold('Syncing challenges')}")
        reporter = ProgressReporter(indent=2)
        reporter.ok(f"Repository: {config.github_repo}")
        reporter.ok(f"Branch: {config.branch}")
        with reporter.step("Fetching repository and discovering challenges"):
            challenges = challenge_service.sync_challenges(git_repo)
        reporter.ok(f"Synced {len(challenges)} challenges")
        stale_count = getattr(challenge_service, "last_sync_disabled_stale_count", 0)
        if stale_count:
            reporter.warn(f"Disabled {stale_count} stale challenge(s)")
        if challenges:
            rows = [
                [challenge.name, _ports_text(challenge_service, challenge), challenge.path]
                for challenge in challenges
            ]
            print(table(["Challenge", "Ports", "Path"], rows, [36, 42, 64]))
        return 0
    except GitError as e:
        print(f"{red(ERR)} Sync failed: {str(e)}")
        return 1
    except ChallengeDiscoveryError as e:
        print(f"{red(ERR)} Sync failed: {str(e)}")
        return 1
    except Exception as e:
        print(f"{red(ERR)} Sync failed: {str(e)}")
        return 1


def cmd_list(args) -> int:
    try:
        config, challenge_service, _, _ = get_services()
        challenges = challenge_service.list_challenges()
        if not challenges:
            print(f"{yellow('No challenges found')}")
            return 0


        show_key = bool(getattr(args, "key", False))
        width = 152 if show_key else 124
        print(f"{'-' * width}")
        if show_key:
            print(f"{'Name':28} {'Primary':16} {'Ports':46} {'Key':24} {'Path'}")
        else:
            print(f"{'Name':28} {'Primary':16} {'Ports':46} {'Path'}")
        print(f"{'-' * width}")
        for challenge in challenges:
            primary = f"{challenge.service_port}/{challenge.service_type}"
            ports_text = _ports_text(challenge_service, challenge)
            if show_key:
                key_text = _key_text(config, challenge)
                print(f"{challenge.name:28} {primary:16} {ports_text:46} {key_text:24} {challenge.path}")
            else:
                print(f"{challenge.name:28} {primary:16} {ports_text:46} {challenge.path}")
        print(f"{'-' * width}")
        return 0
    except Exception as e:
        print(f"{red(ERR)} List failed: {str(e)}")
        return 1


def cmd_inspect(args) -> int:
    try:
        config, challenge_service, runtime_service, export_manager = get_services()
        challenge = challenge_service.get_challenge(args.name)
        if not challenge:
            print(f"{red(ERR)} Challenge not found: {args.name}")
            return 1

        container_port = get_container_port(config, challenge)
        ports = challenge_service.list_challenge_ports(args.name)
        ports_text = ", ".join(f"{p.host_port}:{p.internal_port}/{p.service_type}" for p in ports) or f"{challenge.service_port}:{container_port}/{challenge.service_type}"
        runtime = runtime_service.status(args.name)
        cooldown = runtime_service.check_restart_cooldown(args.name)
        exports = export_manager.list_exports(args.name, check_health=True)
        ttl_text, ttl_ok = ttl_remaining(runtime.expires_at)
        protocol = str(challenge.service_type or "-").upper()
        base_ip = str(getattr(config, "base_ip", "") or "").strip() or "Not configured"
        base_ip_status = green(base_ip) if base_ip != "Not configured" else yellow(base_ip)
        ngrok_status = green("Available") if export_manager.ngrok_available() else yellow("No token/config")
        if not getattr(config, "enable_ngrok", True):
            ngrok_status = red("Disabled")
        localtunnel_status = green("Enabled") if getattr(config, "enable_localtunnel", True) else red("Disabled")
        pinggy_status = green("Enabled") if getattr(config, "enable_pinggy", True) else red("Disabled")
        cloudflare_status = green("Enabled") if getattr(config, "enable_cloudflare", False) else red("Disabled")
        bore_status = green("Enabled") if getattr(config, "enable_bore", True) else red("Disabled")
        restart_cd = yellow(f"{format_duration(cooldown)} left") if cooldown else green("Ready")
        ttl_value = green(ttl_text) if ttl_ok and ttl_text != "-" else red("Expired") if ttl_text != "-" else "-"
        print(panel(
            f"Challenge: {challenge.name}",
            [
                ("Path", challenge.path),
                ("Type", protocol),
                ("Internal Port", container_port),
                ("Host Port", challenge.service_port),
                ("Ports", ports_text),
                ("Enabled", green("Yes") if challenge.enabled else red("No")),
                ("Created", format_datetime(challenge.created_at)),
            ],
        ))
        print(panel(
            "Configuration",
            [
                ("Base IP", base_ip_status),
                ("Ngrok", ngrok_status),
                ("Localtunnel", localtunnel_status),
                ("Pinggy", pinggy_status),
                ("Cloudflare", cloudflare_status),
                ("Bore", bore_status),
                ("Auto Export", green("Enabled")),
                ("Auto Heal", green("Enabled") if getattr(config, "auto_heal_exports", False) else red("Disabled")),
            ],
        ))
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
        print(box("Active Exports", exports_table(exports, detailed=True), width=116))
        return 0
    except Exception as e:
        print(f"{red(ERR)} Inspect failed: {str(e)}")
        return 1


def cmd_add(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        challenge = challenge_service.add_challenge(args.name, args.path, args.port, args.type)
        print(f"{green(OK)} Added challenge: {challenge.name}")
        return 0
    except Exception as e:
        print(f"{red(ERR)} Add failed: {str(e)}")
        return 1


def cmd_remove(args) -> int:
    try:
        _, challenge_service, _, _ = get_services()
        if not challenge_service.remove_challenge(args.name):
            print(f"{red(ERR)} Challenge not found: {args.name}")
            return 1
        print(f"{green(OK)} Removed challenge: {args.name}")
        return 0
    except Exception as e:
        print(f"{red(ERR)} Remove failed: {str(e)}")
        return 1
