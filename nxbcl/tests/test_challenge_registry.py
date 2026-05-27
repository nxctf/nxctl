from pathlib import Path

from nxbcl.launcher.challenges.registry import ChallengeRegistry


def write_challenge(path: Path, challenge_id: str, name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "challenge.yml").write_text(
        f"id: {challenge_id}\nname: {name}\nrpc_internal: http://anvil:8545\n",
        encoding="utf-8",
    )


def test_registry_reads_multi_challenge_repo_cloned_to_chall_dir(tmp_path):
    fallback_dir = tmp_path / "fallback"
    chall_dir = tmp_path / "chall"

    write_challenge(fallback_dir / "04-convergence", "04-convergence", "Fallback")
    write_challenge(
        chall_dir / "challenges" / "01-convergence-seed",
        "01-convergence-seed",
        "Convergence Seed",
    )
    write_challenge(
        chall_dir / "challenges" / "02-convergence",
        "02-convergence",
        "Convergence",
    )

    registry = ChallengeRegistry(chall_dir, fallback_dir)
    challenges = registry.list_challenges()

    assert [challenge["id"] for challenge in challenges] == [
        "01-convergence-seed",
        "02-convergence",
    ]
    assert registry.get_challenge("01-convergence-seed")["name"] == "Convergence Seed"
    assert registry.get_challenge("02-convergence")["name"] == "Convergence"
    assert registry.get_challenge("04-convergence") is None


def test_registry_still_reads_repo_nested_below_chall_dir(tmp_path):
    fallback_dir = tmp_path / "fallback"
    chall_dir = tmp_path / "chall"

    write_challenge(
        chall_dir / "_nxbcl_nxctl" / "challenges" / "01-convergence-seed",
        "01-convergence-seed",
        "Convergence Seed",
    )

    registry = ChallengeRegistry(chall_dir, fallback_dir)

    assert registry.get_challenge("01-convergence-seed")["name"] == "Convergence Seed"


def test_registry_prefers_synced_repo_over_fallback(tmp_path):
    fallback_dir = tmp_path / "fallback"
    chall_dir = tmp_path / "chall"

    write_challenge(fallback_dir / "02-convergence", "02-convergence", "Old")
    write_challenge(
        chall_dir / "challenges" / "02-convergence",
        "02-convergence",
        "Synced",
    )

    registry = ChallengeRegistry(chall_dir, fallback_dir)

    assert registry.get_challenge("02-convergence")["name"] == "Synced"
    assert registry.list_challenges()[0]["name"] == "Synced"


def test_registry_uses_fallback_when_no_synced_challenges(tmp_path):
    fallback_dir = tmp_path / "fallback"
    chall_dir = tmp_path / "chall"

    write_challenge(fallback_dir / "04-convergence", "04-convergence", "Fallback")

    registry = ChallengeRegistry(chall_dir, fallback_dir)

    assert registry.list_challenges()[0]["id"] == "04-convergence"
    assert registry.get_challenge("04-convergence")["name"] == "Fallback"
