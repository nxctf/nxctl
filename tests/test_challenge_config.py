import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nxctl.core.challenge_config import load_inherited_challenge_config


class ChallengeConfigInheritanceTests(unittest.TestCase):
    def test_nested_nxctl_yml_overrides_only_defined_fields(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            challenge_dir = repo_root / "web" / "sqli"
            challenge_dir.mkdir(parents=True)

            (repo_root / "nxctl.yml").write_text(
                "\n".join(
                    [
                        "key: root-key",
                        "ttl:",
                        "  default_minutes: 30",
                        "  extend_minutes: 5",
                        "lifecycle:",
                        "  can_restart: false",
                    ]
                ),
                encoding="utf-8",
            )
            (repo_root / "web" / "nxctl.yml").write_text(
                "\n".join(
                    [
                        "ttl:",
                        "  extend_minutes: 15",
                    ]
                ),
                encoding="utf-8",
            )
            (challenge_dir / "nxctl.yml").write_text(
                "\n".join(
                    [
                        "lifecycle:",
                        "  restart_cooldown_seconds: 120",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_inherited_challenge_config(challenge_dir, repo_root)

        self.assertEqual(config.key, "root-key")
        self.assertEqual(config.key_source, "nxctl.yml")
        self.assertEqual(config.ttl["default_minutes"], 30)
        self.assertEqual(config.ttl["extend_minutes"], 15)
        self.assertNotIn("extend_threshold_minutes", config.ttl)
        self.assertFalse(config.can_restart)
        self.assertEqual(config.restart_cooldown_seconds, 120)
        self.assertEqual(
            config.config_sources,
            ["nxctl.yml", "web/nxctl.yml", "web/sqli/nxctl.yml"],
        )

    def test_legacy_key_files_do_not_block_nxctl_yml_inheritance(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            challenge_dir = repo_root / "misc" / "warmup"
            challenge_dir.mkdir(parents=True)

            (repo_root / "key").write_text("legacy-root-key", encoding="utf-8")
            (challenge_dir / "key").write_text("legacy-local-key", encoding="utf-8")
            (repo_root / "nxctl.yml").write_text("key: nxctl-root-key", encoding="utf-8")

            config = load_inherited_challenge_config(challenge_dir, repo_root)

        self.assertEqual(config.key, "nxctl-root-key")
        self.assertEqual(config.key_source, "nxctl.yml")
        self.assertEqual(config.config_sources, ["nxctl.yml"])


if __name__ == "__main__":
    unittest.main()
