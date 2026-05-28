import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional


class ChallengeRegistry:
    def __init__(self, chall_dir: Path, fallback_dir: Path):
        self.chall_dir = Path(chall_dir)
        self.fallback_dir = Path(fallback_dir)

    def _load_challenge_yml(self, file_path: Path) -> Optional[Dict[str, Any]]:
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    # Ensure challenge_id is set. Fallback to folder name if missing.
                    if "id" not in data:
                        data["id"] = file_path.parent.name
                    return data
        except Exception:
            pass
        return None

    def _scan_base_dir(self, base_dir: Path) -> Dict[str, Dict[str, Any]]:
        """Scan challenge folders and challenge repos cloned into chall_dir."""
        challenges: Dict[str, Dict[str, Any]] = {}

        if not base_dir.exists():
            return challenges

        root_cfg = self._load_challenge_yml(base_dir / "challenge.yml")
        if root_cfg:
            challenges[root_cfg["id"]] = root_cfg

        root_challenges_dir = base_dir / "challenges"
        if root_challenges_dir.exists():
            for nested in root_challenges_dir.iterdir():
                if not nested.is_dir():
                    continue
                nested_cfg = self._load_challenge_yml(nested / "challenge.yml")
                if nested_cfg:
                    challenges[nested_cfg["id"]] = nested_cfg

        for sub in base_dir.iterdir():
            if not sub.is_dir():
                continue

            direct_cfg = self._load_challenge_yml(sub / "challenge.yml")
            if direct_cfg:
                challenges[direct_cfg["id"]] = direct_cfg

            nested_dir = sub / "challenges"
            if not nested_dir.exists():
                continue

            for nested in nested_dir.iterdir():
                if not nested.is_dir():
                    continue
                nested_cfg = self._load_challenge_yml(nested / "challenge.yml")
                if nested_cfg:
                    challenges[nested_cfg["id"]] = nested_cfg

        return challenges

    def _find_challenge(self, base_dir: Path, challenge_id: str) -> Optional[Dict[str, Any]]:
        if not base_dir.exists():
            return None

        root = self._load_challenge_yml(base_dir / "challenge.yml")
        if root and root.get("id") == challenge_id:
            return root

        root_nested = self._load_challenge_yml(
            base_dir / "challenges" / challenge_id / "challenge.yml"
        )
        if root_nested:
            return root_nested

        direct = self._load_challenge_yml(base_dir / challenge_id / "challenge.yml")
        if direct:
            return direct

        for sub in base_dir.iterdir():
            if not sub.is_dir():
                continue
            nested = self._load_challenge_yml(
                sub / "challenges" / challenge_id / "challenge.yml"
            )
            if nested:
                return nested

        return None

    def list_challenges(self) -> List[Dict[str, Any]]:
        """List synced challenges, falling back to bundled examples only when empty."""
        challenges = self._scan_base_dir(self.chall_dir)
        if not challenges:
            challenges = self._scan_base_dir(self.fallback_dir)

        return sorted(challenges.values(), key=lambda x: x.get("id", ""))

    def get_challenge(self, challenge_id: str) -> Optional[Dict[str, Any]]:
        """Get challenge by ID."""
        cfg = self._find_challenge(self.chall_dir, challenge_id)
        if cfg:
            return cfg

        if self._scan_base_dir(self.chall_dir):
            return None

        cfg = self._find_challenge(self.fallback_dir, challenge_id)
        if cfg:
            return cfg

        return None
