"""Repository sync orchestration with lifecycle-safe runtime updates."""

from dataclasses import dataclass, field
from pathlib import Path

from nxctl.core.git import GitRepository
from nxctl.core.models import Challenge
from nxctl.core.utils import LifecycleLock
from nxctl.core.yaml import extract_ports_from_compose


@dataclass
class SyncRuntimeResult:
    challenge: str
    status: str
    error: str = ""


@dataclass
class SyncResult:
    challenges: list[Challenge]
    old_revision: str | None
    new_revision: str | None
    changed_files: list[str] = field(default_factory=list)
    runtime_results: list[SyncRuntimeResult] = field(default_factory=list)
    disabled_stale: int = 0

    @property
    def repository_changed(self) -> bool:
        return bool(
            self.old_revision
            and self.new_revision
            and self.old_revision != self.new_revision
        )


class ChallengeSyncService:
    """Coordinate Git, catalog, and running runtime updates under one lock."""

    def __init__(self, config, challenge_service, runtime_service):
        self.config = config
        self.challenge_service = challenge_service
        self.runtime_service = runtime_service

    def sync(self, git_repo: GitRepository, auto_restart: bool = True) -> SyncResult:
        with LifecycleLock(self.config, blocking=True):
            old_revision = self._safe_revision(git_repo)
            challenges = self.challenge_service.sync_challenges(git_repo)
            new_revision = self._safe_revision(git_repo)
            changed_files = self._changed_files(git_repo, old_revision, new_revision)

            result = SyncResult(
                challenges=challenges,
                old_revision=old_revision,
                new_revision=new_revision,
                changed_files=changed_files,
                disabled_stale=getattr(
                    self.challenge_service,
                    "last_sync_disabled_stale_count",
                    0,
                ),
            )
            if auto_restart and changed_files:
                result.runtime_results = self._update_running_challenges(
                    challenges,
                    changed_files,
                )
            return result

    def _safe_revision(self, git_repo: GitRepository) -> str | None:
        if not git_repo._is_git_repository(git_repo.local_path):
            return None
        try:
            return git_repo.get_commit_hash()
        except Exception:
            return None

    def _changed_files(
        self,
        git_repo: GitRepository,
        old_revision: str | None,
        new_revision: str | None,
    ) -> list[str]:
        if not old_revision or not new_revision or old_revision == new_revision:
            return []
        return git_repo.changed_files(old_revision, new_revision)

    def _update_running_challenges(
        self,
        challenges: list[Challenge],
        changed_files: list[str],
    ) -> list[SyncRuntimeResult]:
        results = []
        for challenge in challenges:
            if not self._challenge_changed(challenge, changed_files):
                continue
            runtime = self.runtime_service.status(challenge.name)
            if runtime.status != "running":
                continue

            try:
                preserved_ports = self.challenge_service.list_challenge_ports(challenge.name)
                self._validate_port_layout(challenge, preserved_ports)
                self.runtime_service.build(challenge.name, no_cache=True)
            except Exception as exc:
                results.append(SyncRuntimeResult(challenge.name, "build_failed", str(exc)))
                continue

            try:
                self.runtime_service.stop(challenge.name, remove_volumes=True)
                self.runtime_service.start(
                    challenge.name,
                    preferred_ports=preserved_ports,
                    preserve_expires_at=runtime.expires_at,
                    reuse_runtime=True,
                    skip_build=True,
                )
                self.runtime_service.update_restart_time(challenge.name)
                results.append(SyncRuntimeResult(challenge.name, "restarted"))
            except Exception as exc:
                results.append(SyncRuntimeResult(challenge.name, "restart_failed", str(exc)))
        return results

    def _challenge_changed(self, challenge: Challenge, changed_files: list[str]) -> bool:
        challenge_path = str(challenge.path or "").replace("\\", "/").strip("/")
        challenge_prefix = f"{challenge_path}/" if challenge_path else ""
        config_sources = {
            source.strip().replace("\\", "/")
            for source in str(challenge.config_source or "").split(",")
            if source.strip()
        }
        for changed_file in changed_files:
            normalized = changed_file.replace("\\", "/").strip("/")
            if not challenge_path:
                return True
            if normalized == challenge_path or normalized.startswith(challenge_prefix):
                return True
            if normalized in config_sources:
                return True
        return False

    def _validate_port_layout(self, challenge: Challenge, preserved_ports) -> None:
        compose_path = Path(self.config.chall_dir) / challenge.path / "docker-compose.yml"
        configured_ports = extract_ports_from_compose(compose_path)
        configured_layout = {
            (int(port["internal_port"]), str(port.get("protocol") or "tcp"))
            for port in configured_ports
        }
        preserved_layout = {
            (int(port.internal_port), str(port.protocol or "tcp"))
            for port in preserved_ports
        }
        if configured_layout != preserved_layout:
            raise RuntimeError(
                "Published port layout changed; runtime was left running. "
                "Restart the container and provider together to apply the new mapping."
            )
