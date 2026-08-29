"""Challenge container and tunnel log access."""

from collections import deque
from dataclasses import dataclass


@dataclass
class TunnelLog:
    provider: str
    port: int
    path: str
    content: str


class ChallengeLogService:
    def __init__(self, challenge_service, runtime_service, export_manager):
        self.challenge_service = challenge_service
        self.runtime_service = runtime_service
        self.export_manager = export_manager

    def select_challenges(self, selector: str | None, all_challenges: bool = False):
        if all_challenges:
            return self.challenge_service.list_challenges_under(selector)
        if not selector:
            raise ValueError("Provide a challenge name/prefix or use --all")

        exact = self.challenge_service.get_challenge(selector)
        if exact:
            return [exact]
        return self.challenge_service.list_challenges_under(selector)

    def container_logs(
        self,
        challenge_name: str,
        service: str | None = None,
        tail: int = 100,
        follow: bool = False,
        since: str | None = None,
    ) -> str:
        services = [service] if service else None
        return self.runtime_service.logs(
            challenge_name,
            services=services,
            tail=tail,
            follow=follow,
            since=since,
        )

    def tunnel_logs(self, challenge_name: str, tail: int = 100) -> list[TunnelLog]:
        logs = []
        for item in self.export_manager.list_export_log_files(challenge_name):
            path = item["path"]
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    lines = deque(handle, maxlen=max(0, int(tail)))
            except OSError:
                continue
            logs.append(
                TunnelLog(
                    provider=str(item["provider"]),
                    port=int(item["port"]),
                    path=str(path),
                    content="".join(lines),
                )
            )
        return logs
