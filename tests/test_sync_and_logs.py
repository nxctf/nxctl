import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.core.models import Challenge, ChallengePort, RuntimeInstance
from nxctl.scripts.log_service import ChallengeLogService
from nxctl.scripts.sync_service import ChallengeSyncService


class NoopLock:
    def __init__(self, _config, blocking=True):
        self.blocking = blocking

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeGitRepository:
    def __init__(self, old_revision, new_revision, changed_files=None):
        self.local_path = Path(".")
        self.revisions = iter([old_revision, new_revision])
        self.files = list(changed_files or [])

    def _is_git_repository(self, _path):
        return True

    def get_commit_hash(self):
        return next(self.revisions)

    def changed_files(self, old_revision, new_revision):
        return list(self.files)


class SyncSafetyTests(unittest.TestCase):
    def _services(self, root: Path, build_error=None):
        challenge_dir = root / "01"
        challenge_dir.mkdir(parents=True)
        (challenge_dir / "docker-compose.yml").write_text(
            "services:\n  web:\n    image: test\n    ports:\n      - '8080:80'\n",
            encoding="utf-8",
        )
        challenge = Challenge(id=1, name="01", path="01", config_source="nxctl.yml")
        ports = [
            ChallengePort(
                challenge_id=1,
                host_port=42000,
                internal_port=80,
                protocol="tcp",
                is_primary=True,
            )
        ]
        challenge_service = SimpleNamespace(
            sync_challenges=Mock(return_value=[challenge]),
            list_challenge_ports=Mock(return_value=ports),
            last_sync_disabled_stale_count=0,
        )
        events = []
        runtime = RuntimeInstance(
            id=1,
            challenge_id=1,
            status="running",
            expires_at=datetime(2030, 1, 1),
        )

        def build(*_args, **_kwargs):
            events.append("build")
            if build_error:
                raise RuntimeError(build_error)

        runtime_service = SimpleNamespace(
            status=Mock(return_value=runtime),
            build=Mock(side_effect=build),
            stop=Mock(side_effect=lambda *_args, **_kwargs: events.append("stop")),
            start=Mock(side_effect=lambda *_args, **_kwargs: events.append("start")),
            update_restart_time=Mock(side_effect=lambda *_args: events.append("timestamp")),
        )
        config = SimpleNamespace(chall_dir=root)
        return config, challenge_service, runtime_service, events

    def test_unchanged_repository_does_not_touch_runtime(self):
        with TemporaryDirectory() as temp_dir:
            config, challenge_service, runtime_service, _ = self._services(Path(temp_dir))
            git_repo = FakeGitRepository("same", "same")

            with patch("nxctl.scripts.sync_service.LifecycleLock", NoopLock):
                result = ChallengeSyncService(
                    config,
                    challenge_service,
                    runtime_service,
                ).sync(git_repo)

            self.assertFalse(result.repository_changed)
            runtime_service.status.assert_not_called()
            runtime_service.build.assert_not_called()
            runtime_service.stop.assert_not_called()

    def test_failed_prebuild_keeps_running_container_untouched(self):
        with TemporaryDirectory() as temp_dir:
            config, challenge_service, runtime_service, events = self._services(
                Path(temp_dir),
                build_error="broken image",
            )
            git_repo = FakeGitRepository("old", "new", ["01/app.py"])

            with patch("nxctl.scripts.sync_service.LifecycleLock", NoopLock):
                result = ChallengeSyncService(
                    config,
                    challenge_service,
                    runtime_service,
                ).sync(git_repo)

            self.assertEqual(events, ["build"])
            self.assertEqual(result.runtime_results[0].status, "build_failed")
            runtime_service.stop.assert_not_called()
            runtime_service.start.assert_not_called()

    def test_successful_update_builds_before_restart_and_skips_second_build(self):
        with TemporaryDirectory() as temp_dir:
            config, challenge_service, runtime_service, events = self._services(Path(temp_dir))
            git_repo = FakeGitRepository("old", "new", ["01/app.py"])

            with patch("nxctl.scripts.sync_service.LifecycleLock", NoopLock):
                result = ChallengeSyncService(
                    config,
                    challenge_service,
                    runtime_service,
                ).sync(git_repo)

            self.assertEqual(events, ["build", "stop", "start", "timestamp"])
            self.assertEqual(result.runtime_results[0].status, "restarted")
            self.assertTrue(runtime_service.start.call_args.kwargs["skip_build"])
            self.assertTrue(runtime_service.start.call_args.kwargs["reuse_runtime"])


class LogSelectorTests(unittest.TestCase):
    def test_exact_name_wins_and_missing_exact_falls_back_to_prefix(self):
        exact = Challenge(name="01", path="01")
        children = [Challenge(name="team/a"), Challenge(name="team/b")]
        challenge_service = SimpleNamespace(
            get_challenge=Mock(side_effect=lambda name: exact if name == "01" else None),
            list_challenges_under=Mock(return_value=children),
        )
        service = ChallengeLogService(challenge_service, object(), object())

        self.assertEqual(service.select_challenges("01"), [exact])
        self.assertEqual(service.select_challenges("team"), children)
        challenge_service.list_challenges_under.assert_called_once_with("team")

    def test_all_passes_optional_prefix_to_subtree_selector(self):
        children = [Challenge(name="btr/01")]
        challenge_service = SimpleNamespace(
            list_challenges_under=Mock(return_value=children),
        )
        service = ChallengeLogService(challenge_service, object(), object())

        self.assertEqual(service.select_challenges("btr", all_challenges=True), children)
        challenge_service.list_challenges_under.assert_called_once_with("btr")


if __name__ == "__main__":
    unittest.main()
