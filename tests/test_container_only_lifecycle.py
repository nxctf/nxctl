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
    def test_fresh_restart_reuses_runtime_port_and_expiry(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            challenge_dir = repo_root / "web" / "lab"
            challenge_dir.mkdir(parents=True)
            (challenge_dir / "docker-compose.yml").write_text(
                "\n".join(
                    [
                        "services:",
                        "  app:",
                        "    image: test-lab",
                        "    ports:",
                        "      - '8080:80'",
                    ]
                ),
                encoding="utf-8",
            )

            db_path = root / "nxctl.db"
            init_database(str(db_path))
            challenge_service = ChallengeService(str(db_path))
            challenges = challenge_service.discover_challenges(repo_root)
            challenge_service._save_challenges_to_db(challenges)
            config = SimpleNamespace(
                compose_dir=root / "runtime" / "compose",
                locks_dir=root / "runtime" / "locks",
                default_ttl_minutes=15,
                extend_time_minutes=10,
                extend_threshold_minutes=5,
                extend_cooldown_seconds=30,
                can_restart=True,
                restart_cooldown_seconds=300,
                local_port_start=40000,
                local_port_end=49999,
                randomize_local_ports=True,
            )
            runtime_service = RuntimeService(config, str(db_path), str(repo_root))

            with (
                patch("nxctl.scripts.runtime_service.run_docker_compose_build"),
                patch("nxctl.scripts.runtime_service.run_docker_compose_up"),
                patch.object(runtime_service, "_allocate_runtime_port", return_value=41000),
            ):
                first_runtime = runtime_service.start("web/lab")

            preserved_ports = challenge_service.list_challenge_ports("web/lab")
            with patch("nxctl.scripts.runtime_service.run_docker_compose_down_with_cleanup"):
                runtime_service.stop("web/lab", remove_volumes=True)

            with (
                patch("nxctl.scripts.runtime_service.run_docker_compose_build"),
                patch("nxctl.scripts.runtime_service.run_docker_compose_up"),
                patch.object(runtime_service, "_wait_for_host_port_available", return_value=True),
                patch.object(runtime_service, "_allocate_runtime_port") as allocate_port,
            ):
                restarted_runtime = runtime_service.start(
                    "web/lab",
                    preferred_ports=preserved_ports,
                    preserve_expires_at=first_runtime.expires_at,
                    reuse_runtime=True,
                )

            self.assertEqual(restarted_runtime.id, first_runtime.id)
            self.assertEqual(restarted_runtime.expires_at, first_runtime.expires_at)
            self.assertEqual(
                challenge_service.list_challenge_ports("web/lab")[0].host_port,
                41000,
            )
            allocate_port.assert_not_called()

    def test_preferred_restart_port_waits_for_docker_release(self):
        service = RuntimeService.__new__(RuntimeService)
        service.config = SimpleNamespace(
            restart_port_release_attempts=3,
            restart_port_release_delay_seconds=0.01,
        )

        with (
            patch("nxctl.scripts.runtime_service.is_port_in_use", side_effect=[True, True, False]),
            patch.object(service, "_host_port_available_for_bind", return_value=True),
            patch("nxctl.scripts.runtime_service.time.sleep") as sleep,
        ):
            available = service._wait_for_host_port_available(40083)

        self.assertTrue(available)
        self.assertEqual(sleep.call_count, 2)

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

    @patch("nxctl.scripts.runtime_service.subprocess.run")
    def test_validate_external_networks_subprocess_check(self, mock_run):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = SimpleNamespace(
                compose_dir=root / "runtime" / "compose",
                locks_dir=root / "runtime" / "locks",
            )
            runtime_service = RuntimeService(config, str(root / "db.sqlite"), str(root))

            mock_run.return_value = SimpleNamespace(returncode=0)
            compose_data = {
                "networks": {
                    "my_net": {
                        "external": True,
                        "name": "custom-ctf-network-name"
                    }
                }
            }
            runtime_service._validate_external_networks(compose_data, "any-challenge")
            mock_run.assert_called_once_with(
                ["docker", "network", "inspect", "custom-ctf-network-name"],
                capture_output=True,
                text=True,
                check=False,
            )


if __name__ == "__main__":
    unittest.main()
