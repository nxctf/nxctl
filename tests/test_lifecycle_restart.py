import sys
import contextlib
import io
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.scripts.cli.lifecycle import _cmd_up_one, restart_challenge_lifecycle
from nxctl.scripts.runtime_service import RuntimeService


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
        runtime_service.start.assert_called_once_with("misc/disabled", force=True, no_cache=False)

    def test_force_restart_bypasses_policy_without_allowing_disabled_start_by_default(self):
        challenge = SimpleNamespace(name="misc/worker", service_port=0, service_type="http")
        challenge_service = SimpleNamespace(
            get_challenge=Mock(return_value=challenge),
            list_challenge_ports=Mock(return_value=[]),
        )
        runtime_service = SimpleNamespace(
            ensure_restart_allowed=Mock(side_effect=RuntimeError("Restart disabled by challenge config")),
            check_restart_cooldown=Mock(return_value=120),
            status=Mock(return_value=SimpleNamespace(status="running", expires_at=datetime(2026, 1, 1, 13, 0, 0))),
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
        runtime_service.stop.assert_called_once_with("misc/worker", remove_volumes=True)
        runtime_service.start.assert_called_once_with(
            "misc/worker",
            force=False,
            no_cache=False,
            preferred_ports=[],
            preserve_expires_at=datetime(2026, 1, 1, 13, 0, 0),
            reuse_runtime=True,
        )
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
            status=Mock(return_value=SimpleNamespace(status="stopped", expires_at=None)),
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

        runtime_service.start.assert_called_once_with(
            "misc/worker",
            force=True,
            no_cache=False,
            preferred_ports=[],
            preserve_expires_at=None,
            reuse_runtime=False,
        )

    def test_default_restart_resets_container_without_restarting_tunnel(self):
        expires_at = datetime(2026, 1, 1, 13, 0, 0)
        ports = [{"host_port": 41000, "internal_port": 80, "protocol": "tcp"}]
        challenge = SimpleNamespace(name="web/lab", service_port=41000, service_type="http")
        challenge_service = SimpleNamespace(
            get_challenge=Mock(return_value=challenge),
            list_challenge_ports=Mock(return_value=ports),
        )
        runtime_service = SimpleNamespace(
            ensure_restart_allowed=Mock(),
            check_restart_cooldown=Mock(return_value=None),
            status=Mock(return_value=SimpleNamespace(status="running", expires_at=expires_at)),
            stop=Mock(),
            start=Mock(),
            update_restart_time=Mock(),
        )
        export_manager = SimpleNamespace(
            list_exports=Mock(),
            stop_export=Mock(),
            start_available_exports=Mock(),
        )

        result = restart_challenge_lifecycle(
            "web/lab",
            challenge_service,
            runtime_service,
            export_manager,
        )

        self.assertEqual(result["scope"], "container")
        runtime_service.stop.assert_called_once_with("web/lab", remove_volumes=True)
        runtime_service.start.assert_called_once_with(
            "web/lab",
            force=False,
            no_cache=False,
            preferred_ports=ports,
            preserve_expires_at=expires_at,
            reuse_runtime=True,
        )
        export_manager.list_exports.assert_not_called()
        export_manager.stop_export.assert_not_called()
        export_manager.start_available_exports.assert_not_called()


class RuntimeCooldownTests(unittest.TestCase):
    def test_restart_cooldown_uses_utc_clock(self):
        utc_now = datetime(2026, 1, 1, 12, 0, 0)
        local_now = utc_now + timedelta(hours=7)
        service = RuntimeService.__new__(RuntimeService)
        service._get_challenge_from_db = Mock(return_value=SimpleNamespace(id=1))
        service._effective_lifecycle_for_challenge = Mock(
            return_value={"restart_cooldown_seconds": 300}
        )
        service._get_runtime_from_db = Mock(
            return_value=SimpleNamespace(last_restart=utc_now - timedelta(seconds=60))
        )

        with patch("nxctl.scripts.runtime_service.datetime") as mocked_datetime:
            mocked_datetime.utcnow.return_value = utc_now
            mocked_datetime.now.return_value = local_now
            remaining = service.check_restart_cooldown("misc/worker")

        self.assertEqual(remaining, 240)

    def test_extend_cooldown_uses_utc_clock(self):
        utc_now = datetime(2026, 1, 1, 12, 0, 0)
        local_now = utc_now + timedelta(hours=7)
        service = RuntimeService.__new__(RuntimeService)
        service._get_challenge_from_db = Mock(return_value=SimpleNamespace(id=1))
        service._effective_ttl_for_challenge = Mock(
            return_value={"extend_cooldown_seconds": 30}
        )
        service._get_runtime_from_db = Mock(
            return_value=SimpleNamespace(last_activity=utc_now - timedelta(seconds=10))
        )

        with patch("nxctl.scripts.runtime_service.datetime") as mocked_datetime:
            mocked_datetime.utcnow.return_value = utc_now
            mocked_datetime.now.return_value = local_now
            remaining = service.check_extend_cooldown("misc/worker")

        self.assertEqual(remaining, 20)


if __name__ == "__main__":
    unittest.main()
