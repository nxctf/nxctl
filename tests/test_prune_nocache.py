import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.core.db import init_database, get_db_connection, close_db_connection
from nxctl.scripts.challenge_service import ChallengeService
from nxctl.scripts.runtime_service import RuntimeService


class PruneNoCacheTests(unittest.TestCase):
    def test_prune_disabled_challenges(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "nxctl.db"
            init_database(str(db_path))

            # Insert test challenges manually into the db to control enabled state
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO challenges (name, path, service_port, enabled) VALUES (?, ?, ?, ?)",
                ("NFCTF/lab-01", "NFCTF/lab-01", 1234, 0) # Disabled
            )
            cursor.execute(
                "INSERT INTO challenges (name, path, service_port, enabled) VALUES (?, ?, ?, ?)",
                ("NFCTF/lab-02", "NFCTF/lab-02", 5678, 1) # Enabled
            )
            cursor.execute(
                "INSERT INTO challenge_ports (challenge_id, host_port, internal_port, service_type) VALUES (?, ?, ?, ?)",
                (1, 1234, 80, "http")
            )
            cursor.execute(
                "INSERT INTO challenge_ports (challenge_id, host_port, internal_port, service_type) VALUES (?, ?, ?, ?)",
                (2, 5678, 80, "http")
            )
            cursor.execute(
                "INSERT INTO runtime_instances (challenge_id, status) VALUES (?, ?)",
                (1, "stopped")
            )
            cursor.execute(
                "INSERT INTO runtime_instances (challenge_id, status) VALUES (?, ?)",
                (2, "running")
            )
            cursor.execute(
                "INSERT INTO challenge_exports (runtime_id, provider, status) VALUES (?, ?, ?)",
                (1, "ngrok", "inactive")
            )
            cursor.execute(
                "INSERT INTO challenge_exports (runtime_id, provider, status) VALUES (?, ?, ?)",
                (2, "ngrok", "active")
            )
            conn.commit()
            close_db_connection(conn)

            challenge_service = ChallengeService(str(db_path))
            
            # Prune
            pruned_count = challenge_service.prune_disabled_challenges()
            self.assertEqual(pruned_count, 1)

            # Check that database matches
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            
            # Enabled challenge is still there
            cursor.execute("SELECT name FROM challenges")
            challenges = [row["name"] for row in cursor.fetchall()]
            self.assertEqual(challenges, ["NFCTF/lab-02"])

            # Disabled challenge ports are gone
            cursor.execute("SELECT host_port FROM challenge_ports")
            ports = [row["host_port"] for row in cursor.fetchall()]
            self.assertEqual(ports, [5678])

            # Disabled challenge runtime instances are gone
            cursor.execute("SELECT challenge_id FROM runtime_instances")
            runtimes = [row["challenge_id"] for row in cursor.fetchall()]
            self.assertEqual(runtimes, [2])

            # Disabled challenge exports are gone
            cursor.execute("SELECT runtime_id FROM challenge_exports")
            exports = [row["runtime_id"] for row in cursor.fetchall()]
            self.assertEqual(exports, [2])

            close_db_connection(conn)

    def test_nocache_propagation_to_build(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            challenge_dir = repo_root / "misc" / "worker"
            challenge_dir.mkdir(parents=True)
            (challenge_dir / "docker-compose.yml").write_text(
                "services:\n  worker:\n    image: busybox\n", encoding="utf-8"
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
            )
            runtime_service = RuntimeService(config, str(db_path), str(repo_root))

            with (
                patch("nxctl.scripts.runtime_service.run_docker_compose_build") as mock_build,
                patch("nxctl.scripts.runtime_service.run_docker_compose_up") as mock_up,
            ):
                runtime_service.start("misc/worker", no_cache=True)
                mock_build.assert_called_once_with(
                    challenge_dir / "docker-compose.yml",
                    cwd=challenge_dir,
                    no_cache=True
                )

    def test_admin_challenges_filters_disabled(self):
        from nxctl_api.routes.challenges import list_admin_challenges
        mock_challenge_enabled = SimpleNamespace(name="enabled-chall", enabled=True, service_port=80, service_type="http")
        mock_challenge_disabled = SimpleNamespace(name="disabled-chall", enabled=False, service_port=80, service_type="http")

        class MockChallengeService:
            def list_challenges(self, include_disabled=False):
                if include_disabled:
                    return [mock_challenge_enabled, mock_challenge_disabled]
                return [mock_challenge_enabled]

        mock_config = SimpleNamespace(state_dir=Path("/tmp"))

        with (
            patch("nxctl_api.routes.challenges.get_services", return_value=(mock_config, MockChallengeService(), None, None)),
            patch("nxctl_api.routes.challenges.serialize_challenge_admin", side_effect=lambda c, cfg: {"name": c.name, "enabled": c.enabled})
        ):
            # Test default: should filter out disabled challenges
            res_default = list_admin_challenges()
            self.assertEqual(res_default, [{"name": "enabled-chall", "enabled": True}])

            # Test include_disabled=True
            res_all = list_admin_challenges(include_disabled=True)
            self.assertEqual(res_all, [
                {"name": "enabled-chall", "enabled": True},
                {"name": "disabled-chall", "enabled": False}
            ])

    def test_prune_all_challenges(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "nxctl.db"
            init_database(str(db_path))

            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO challenges (name, path, service_port, enabled) VALUES (?, ?, ?, ?)",
                ("NFCTF/lab-01", "NFCTF/lab-01", 1234, 0) # Disabled
            )
            cursor.execute(
                "INSERT INTO challenges (name, path, service_port, enabled) VALUES (?, ?, ?, ?)",
                ("NFCTF/lab-02", "NFCTF/lab-02", 5678, 1) # Enabled
            )
            conn.commit()
            close_db_connection(conn)

            challenge_service = ChallengeService(str(db_path))
            
            # Prune all
            pruned_count = challenge_service.prune_disabled_challenges(all_challenges=True)
            self.assertEqual(pruned_count, 2)

            # Check that database is empty
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM challenges")
            challenges = cursor.fetchall()
            self.assertEqual(len(challenges), 0)
            close_db_connection(conn)
