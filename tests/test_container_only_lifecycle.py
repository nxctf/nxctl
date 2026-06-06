import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.core.db import init_database
from nxctl.scripts.challenge_service import ChallengeService
from nxctl.scripts.cli.lifecycle import _start_available_exports
from nxctl.scripts.runtime_service import RuntimeService


class ContainerOnlyLifecycleTests(unittest.TestCase):
    def test_compose_without_ports_starts_without_exports_or_allocated_ports(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            challenge_dir = repo_root / "misc" / "worker"
            challenge_dir.mkdir(parents=True)
            (challenge_dir / "docker-compose.yml").write_text(
                "\n".join(
                    [
                        "services:",
                        "  worker:",
                        "    image: busybox",
                        "    command: ['sh', '-c', 'sleep 3600']",
                    ]
                ),
                encoding="utf-8",
            )

            db_path = root / "nxctl.db"
            init_database(str(db_path))
            challenge_service = ChallengeService(str(db_path))
            challenges = challenge_service.discover_challenges(repo_root)
            challenge_service._save_challenges_to_db(challenges)

            challenge = challenge_service.get_challenge("misc/worker")
            self.assertIsNotNone(challenge)
            self.assertEqual(challenge.service_port, 0)
            self.assertEqual(challenge_service.list_challenge_ports("misc/worker"), [])

            config = SimpleNamespace(
                compose_dir=root / "runtime" / "compose",
                locks_dir=root / "runtime" / "locks",
                default_ttl_minutes=15,
                extend_time_minutes=10,
                extend_threshold_minutes=5,
                extend_cooldown_seconds=30,
                can_restart=True,
                restart_cooldown_seconds=300,
            )
            runtime_service = RuntimeService(config, str(db_path), str(repo_root))

            with (
                patch("nxctl.scripts.runtime_service.run_docker_compose_build"),
                patch("nxctl.scripts.runtime_service.run_docker_compose_up"),
                patch.object(runtime_service, "_allocate_runtime_port") as allocate_port,
            ):
                runtime = runtime_service.start("misc/worker")

            self.assertEqual(runtime.status, "running")
            allocate_port.assert_not_called()
            self.assertEqual(challenge_service.list_challenge_ports("misc/worker"), [])
            self.assertEqual(challenge_service.get_challenge("misc/worker").service_port, 0)

            export_manager = SimpleNamespace(
                config=config,
                start_available_exports=Mock(),
            )
            exports, failures = _start_available_exports(
                export_manager,
                "misc/worker",
                challenge_service.get_challenge("misc/worker"),
                challenge_service.list_challenge_ports("misc/worker"),
            )
            self.assertEqual(exports, [])
            self.assertEqual(failures, [])
            export_manager.start_available_exports.assert_not_called()

    def test_sync_saves_inherited_enabled_flag(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            disabled_dir = repo_root / "misc" / "disabled"
            enabled_dir = repo_root / "misc" / "enabled"
            disabled_dir.mkdir(parents=True)
            enabled_dir.mkdir(parents=True)
            (repo_root / "nxctl.yml").write_text("enabled: false", encoding="utf-8")
            (enabled_dir / "nxctl.yml").write_text("enable: true", encoding="utf-8")
            compose = "\n".join(
                [
                    "services:",
                    "  app:",
                    "    image: busybox",
                    "    command: ['sh', '-c', 'sleep 3600']",
                ]
            )
            (disabled_dir / "docker-compose.yml").write_text(compose, encoding="utf-8")
            (enabled_dir / "docker-compose.yml").write_text(compose, encoding="utf-8")

            db_path = root / "nxctl.db"
            init_database(str(db_path))
            challenge_service = ChallengeService(str(db_path))
            challenges = challenge_service.discover_challenges(repo_root)
            challenge_service._save_challenges_to_db(challenges)

            self.assertFalse(challenge_service.get_challenge("misc/disabled").enabled)
            self.assertTrue(challenge_service.get_challenge("misc/enabled").enabled)


if __name__ == "__main__":
    unittest.main()
