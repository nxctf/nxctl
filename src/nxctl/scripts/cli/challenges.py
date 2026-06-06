"""CLI command handlers for challenge management."""

import logging
from nxctl.core.challenge_config import read_config_key
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
    if not challenge.service_port:
        return "container-only"
    return f"{challenge.service_port}/{challenge.service_type}"


def _primary_text(challenge) -> str:
    if not challenge.service_port:
        return "-"
    return f"{challenge.service_port}/{challenge.service_type}"


def _key_text(config, challenge) -> str:
    if not challenge.access_key_hash:
        return "No"

    key_source = str(challenge.access_key_source or "").strip()
    if not key_source:
        return "(unavailable)"

    key_path = (config.chall_dir / key_source).resolve()
    try:
        return read_config_key(key_path) or "(empty)"
    except Exception:
        return "(unavailable)"


def _key_status_text(challenge) -> str:
    return "Yes" if challenge.access_key_hash else "No"


def _config_source_text(challenge) -> str:
    return str(getattr(challenge, "config_source", "") or "-")


def _config_int(config, attr: str, default: int) -> int:
    value = getattr(config, attr, default)
    if value is None:
        return default
    return int(value)


def _effective_ttl(config, challenge) -> dict[str, int]:
    return {
        "default_minutes": int(
            challenge.ttl_default_minutes
            if challenge.ttl_default_minutes is not None
            else _config_int(config, "default_ttl_minutes", 15)
        ),
        "extend_minutes": int(
            challenge.ttl_extend_minutes
            if challenge.ttl_extend_minutes is not None
            else _config_int(config, "extend_time_minutes", 10)
        ),
        "extend_threshold_minutes": int(
            challenge.ttl_extend_threshold_minutes
            if challenge.ttl_extend_threshold_minutes is not None
            else _config_int(config, "extend_threshold_minutes", 5)
        ),
        "extend_cooldown_seconds": int(
            challenge.ttl_extend_cooldown_seconds
            if challenge.ttl_extend_cooldown_seconds is not None
            else _config_int(config, "extend_cooldown_seconds", 30)
        ),
    }


def _ttl_summary(config, challenge) -> str:
    ttl = _effective_ttl(config, challenge)
    return (
        f"{ttl['default_minutes']}m/"
        f"+{ttl['extend_minutes']}m/"
        f"<={ttl['extend_threshold_minutes']}m/"
        f"{ttl['extend_cooldown_seconds']}s"
    )


def _effective_lifecycle(config, challenge) -> dict[str, int | bool]:
    can_restart = getattr(challenge, "can_restart", None)
    if can_restart is None:
        can_restart = bool(getattr(config, "can_restart", True))

    cooldown = getattr(challenge, "restart_cooldown_seconds", None)
    if cooldown is None:
        cooldown = _config_int(config, "restart_cooldown_seconds", 300)

    return {
        "can_restart": bool(can_restart),
        "restart_cooldown_seconds": int(cooldown),
    }


def _restart_policy_text(config, challenge) -> str:
    lifecycle = _effective_lifecycle(config, challenge)
    status = "Enabled" if lifecycle["can_restart"] else "Disabled"
    return f"{status}/{format_duration(lifecycle['restart_cooldown_seconds'])}"


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
        show_all = bool(getattr(args, "all", False))
        rows = []
        if show_all:
            for challenge in challenges:
                rows.append([
                    challenge.name,
                    _primary_text(challenge),
                    _ports_text(challenge_service, challenge),
                    _key_text(config, challenge) if show_key else _key_status_text(challenge),
                    _ttl_summary(config, challenge),
                    _restart_policy_text(config, challenge),
                    _config_source_text(challenge),
                    challenge.path,
                ])
            print(table(
                ["Name", "Primary", "Ports", "Key", "TTL", "Restart", "Config", "Path"],
                rows,
                [28, 16, 42, 24, 20, 10, 34, 54],
            ))
        elif show_key:
            for challenge in challenges:
                rows.append([
                    challenge.name,
                    _primary_text(challenge),
                    _ports_text(challenge_service, challenge),
                    _key_text(config, challenge),
                    challenge.path,
                ])
            print(table(["Name", "Primary", "Ports", "Key", "Path"], rows, [28, 16, 46, 24, 64]))
        else:
            for challenge in challenges:
                rows.append([
                    challenge.name,
                    _primary_text(challenge),
                    _ports_text(challenge_service, challenge),
                    challenge.path,
                ])
            print(table(["Name", "Primary", "Ports", "Path"], rows, [28, 16, 46, 64]))
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
        ports_text = ", ".join(f"{p.host_port}:{p.internal_port}/{p.service_type}" for p in ports) or "container-only"
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
        effective_ttl = _effective_ttl(config, challenge)
        effective_lifecycle = _effective_lifecycle(config, challenge)
        if not effective_lifecycle["can_restart"]:
            restart_cd = red("Disabled")
        print(panel(
            f"Challenge: {challenge.name}",
            [
                ("Path", challenge.path),
                ("Type", protocol),
                ("Internal Port", container_port if challenge.service_port else "-"),
                ("Host Port", challenge.service_port or "-"),
                ("Ports", ports_text),
                ("Enabled", green("Yes") if challenge.enabled else red("No")),
                ("Key Required", green("Yes") if challenge.access_key_hash else "No"),
                ("Config Source", _config_source_text(challenge)),
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
                ("TTL Default", f"{effective_ttl['default_minutes']}m"),
                ("TTL Extend", f"{effective_ttl['extend_minutes']}m"),
                ("Extend Window", f"{effective_ttl['extend_threshold_minutes']}m"),
                ("Extend Cooldown", format_duration(effective_ttl["extend_cooldown_seconds"])),
                ("Restart", green("Enabled") if effective_lifecycle["can_restart"] else red("Disabled")),
                ("Restart Cooldown", format_duration(effective_lifecycle["restart_cooldown_seconds"])),
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
