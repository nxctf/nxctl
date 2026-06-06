import sys
import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.scripts.cli.lifecycle import _cmd_up_one, restart_challenge_lifecycle


class RestartLifecycleTests(unittest.TestCase):
    def test_cli_up_force_passes_force_to_runtime_start(self):
        challenge = SimpleNamespace(
            name="misc/disabled",
            enabled=False,
            service_port=0,
            service_type="http",
        )
        challenge_service = SimpleNamespace(
            get_challenge=Mock(return_value=challenge),
            list_challenge_ports=Mock(return_value=[]),
        )
        runtime_service = SimpleNamespace(
            start=Mock(),
            status=Mock(return_value=SimpleNamespace(expires_at=None)),
        )
        with TemporaryDirectory() as temp_dir:
            export_manager = SimpleNamespace(
                config=SimpleNamespace(locks_dir=Path(temp_dir) / "locks"),
                start_available_exports=Mock(return_value=([], [])),
            )

            with contextlib.redirect_stdout(io.StringIO()):
                ok = _cmd_up_one(
                    "misc/disabled",
                    challenge_service,
                    runtime_service,
                    export_manager,
                    force=True,
                )

        self.assertTrue(ok)
        runtime_service.start.assert_called_once_with("misc/disabled", force=True)

    def test_force_restart_bypasses_policy_without_allowing_disabled_start_by_default(self):
        challenge = SimpleNamespace(name="misc/worker", service_port=0, service_type="http")
        challenge_service = SimpleNamespace(
            get_challenge=Mock(return_value=challenge),
            list_challenge_ports=Mock(return_value=[]),
        )
        runtime_service = SimpleNamespace(
            ensure_restart_allowed=Mock(side_effect=RuntimeError("Restart disabled by challenge config")),
            check_restart_cooldown=Mock(return_value=120),
            stop=Mock(),
            start=Mock(),
            update_restart_time=Mock(),
        )
        export_manager = SimpleNamespace(
            list_exports=Mock(return_value=[]),
            start_available_exports=Mock(return_value=([], [])),
        )

        result = restart_challenge_lifecycle(
            "misc/worker",
            challenge_service,
            runtime_service,
            export_manager,
            container=True,
            force=True,
        )

        self.assertTrue(result["force"])
        runtime_service.ensure_restart_allowed.assert_not_called()
        runtime_service.check_restart_cooldown.assert_not_called()
        runtime_service.stop.assert_called_once_with("misc/worker")
        runtime_service.start.assert_called_once_with("misc/worker", force=False)
        runtime_service.update_restart_time.assert_called_once_with("misc/worker")

    def test_cli_force_restart_can_explicitly_allow_disabled_start(self):
        challenge = SimpleNamespace(name="misc/worker", service_port=0, service_type="http")
        challenge_service = SimpleNamespace(
            get_challenge=Mock(return_value=challenge),
            list_challenge_ports=Mock(return_value=[]),
        )
        runtime_service = SimpleNamespace(
            ensure_restart_allowed=Mock(),
            check_restart_cooldown=Mock(),
            stop=Mock(),
            start=Mock(),
            update_restart_time=Mock(),
        )
        export_manager = SimpleNamespace()

        restart_challenge_lifecycle(
            "misc/worker",
            challenge_service,
            runtime_service,
            export_manager,
            container=True,
            force=True,
            start_disabled=True,
        )

        runtime_service.start.assert_called_once_with("misc/worker", force=True)


if __name__ == "__main__":
    unittest.main()
