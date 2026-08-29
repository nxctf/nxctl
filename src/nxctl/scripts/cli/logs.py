"""CLI handler for challenge and tunnel logs."""

from nxctl.scripts.cli.base import get_services
from nxctl.scripts.cli.render import ERR
from nxctl.scripts.log_service import ChallengeLogService
from nxctl.core.utils import bold, red, yellow


def cmd_logs(args) -> int:
    try:
        _, challenge_service, runtime_service, export_manager = get_services()
        log_service = ChallengeLogService(
            challenge_service,
            runtime_service,
            export_manager,
        )
        challenges = log_service.select_challenges(
            getattr(args, "name", None),
            all_challenges=bool(getattr(args, "all", False)),
        )
        if not challenges:
            print(yellow("No matching challenges found"))
            return 1

        service = getattr(args, "service", None)
        follow = bool(getattr(args, "follow", False))
        source = str(getattr(args, "source", "all") or "all")
        tail = max(0, int(getattr(args, "tail", 100)))
        since = getattr(args, "since", None)

        if service and len(challenges) != 1:
            print(f"{red(ERR)} A Compose service can only be selected for one exact challenge")
            return 1
        if follow and len(challenges) != 1:
            print(f"{red(ERR)} --follow requires one exact challenge")
            return 1
        if follow and source == "tunnel":
            print(f"{red(ERR)} --follow currently requires container logs")
            return 1

        had_errors = False
        for challenge in challenges:
            print(bold(f"[{challenge.name}]"))

            if source in {"all", "tunnel"}:
                tunnel_logs = log_service.tunnel_logs(challenge.name, tail=tail)
                if not tunnel_logs:
                    print(yellow("  No tunnel logs found"))
                for tunnel_log in tunnel_logs:
                    print(bold(f"  tunnel/{tunnel_log.provider}:{tunnel_log.port}"))
                    if tunnel_log.content:
                        print(tunnel_log.content, end="" if tunnel_log.content.endswith("\n") else "\n")

            if source in {"all", "container"}:
                print(bold("  container"))
                try:
                    output = log_service.container_logs(
                        challenge.name,
                        service=service,
                        tail=tail,
                        follow=follow,
                        since=since,
                    )
                    if output:
                        print(output, end="" if output.endswith("\n") else "\n")
                    elif not follow:
                        print(yellow("  No container logs found"))
                except Exception as exc:
                    had_errors = True
                    print(f"{red(ERR)} {exc}")

        return 1 if had_errors else 0
    except ValueError as exc:
        print(f"{red(ERR)} {exc}")
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"{red(ERR)} Logs failed: {exc}")
        return 1
