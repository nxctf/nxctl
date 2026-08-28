import contextlib
import io
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.core.db import close_db_connection, get_db_connection, init_database
from nxctl.scripts.challenge_service import ChallengeService
from nxctl.scripts.cli.lifecycle import cmd_up
from nxctl_api.routes.lifecycle import up_all_challenges


class CountingLock:
    entered = 0

    def __init__(self, _config):
        pass

    def __enter__(self):
        type(self).entered += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class ChallengePrefixTests(unittest.TestCase):
    def test_prefix_matches_only_exact_path_subtree_and_enabled_challenges(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "nxctl.db"
            init_database(str(db_path))
            conn = get_db_connection(str(db_path))
            conn.executemany(
                "INSERT INTO challenges (name, path, service_port, enabled) VALUES (?, ?, 0, ?)",
                [
                    ("01", "01", 1),
                    ("01/web", "01/web", 1),
                    ("01/pwn/deep", "01/pwn/deep", 1),
                    ("01/disabled", "01/disabled", 0),
                    ("010", "010", 1),
                    ("team/01", "team/01", 1),
                ],
            )
            conn.commit()
            close_db_connection(conn)

            service = ChallengeService(str(db_path))
            names = [challenge.name for challenge in service.list_challenges_under("/01/")]

            self.assertEqual(names, ["01", "01/pwn/deep", "01/web"])
            with self.assertRaises(ValueError):
                service.list_challenges_under("01/../team")


class BatchUpLockTests(unittest.TestCase):
    def setUp(self):
        CountingLock.entered = 0

    def test_cli_acquires_lifecycle_lock_once_per_selected_challenge(self):
        challenges = [SimpleNamespace(name="01/a"), SimpleNamespace(name="01/b")]
        challenge_service = SimpleNamespace(
            list_challenges_under=Mock(return_value=challenges),
        )
        args = SimpleNamespace(all=True, name="01", no_cache=False)

        with (
            patch(
                "nxctl.scripts.cli.lifecycle.get_services",
                return_value=(object(), challenge_service, object(), object()),
            ),
            patch("nxctl.scripts.cli.lifecycle.LifecycleLock", CountingLock),
            patch("nxctl.scripts.cli.lifecycle._cmd_up_one", return_value=True) as start_one,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            exit_code = cmd_up(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(CountingLock.entered, 2)
        challenge_service.list_challenges_under.assert_called_once_with("01")
        self.assertEqual([call.args[0] for call in start_one.call_args_list], ["01/a", "01/b"])

    def test_cli_prefix_without_matches_fails_without_taking_lock(self):
        challenge_service = SimpleNamespace(
            list_challenges_under=Mock(return_value=[]),
        )
        args = SimpleNamespace(all=True, name="missing", no_cache=False)

        with (
            patch(
                "nxctl.scripts.cli.lifecycle.get_services",
                return_value=(object(), challenge_service, object(), object()),
            ),
            patch("nxctl.scripts.cli.lifecycle.LifecycleLock", CountingLock),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            exit_code = cmd_up(args)

        self.assertEqual(exit_code, 1)
        self.assertEqual(CountingLock.entered, 0)

    def test_api_acquires_lifecycle_lock_once_per_selected_challenge(self):
        challenges = [SimpleNamespace(name="01/a"), SimpleNamespace(name="01/b")]
        challenge_service = SimpleNamespace(
            list_challenges_under=Mock(return_value=challenges),
        )

        with (
            patch(
                "nxctl_api.routes.lifecycle.get_services",
                return_value=(object(), challenge_service, object(), object()),
            ),
            patch("nxctl_api.routes.lifecycle.LifecycleLock", CountingLock),
            patch(
                "nxctl_api.routes.lifecycle.start_challenge_payload",
                side_effect=lambda name, *_args: {"challenge": name},
            ),
        ):
            result = up_all_challenges(all=True, prefix="01")

        self.assertTrue(result["ok"])
        self.assertEqual(result["started"], 2)
        self.assertEqual(CountingLock.entered, 2)
        challenge_service.list_challenges_under.assert_called_once_with("01")

    def test_api_prefix_without_matches_returns_not_found(self):
        challenge_service = SimpleNamespace(
            list_challenges_under=Mock(return_value=[]),
        )

        with patch(
            "nxctl_api.routes.lifecycle.get_services",
            return_value=(object(), challenge_service, object(), object()),
        ):
            with self.assertRaises(HTTPException) as raised:
                up_all_challenges(all=True, prefix="missing")

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
