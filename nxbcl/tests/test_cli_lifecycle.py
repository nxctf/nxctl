from pathlib import Path
from types import SimpleNamespace

from nxbcl.cli import main as cli_main


def test_cleanup_runtime_artifacts_removes_state_files(tmp_path, monkeypatch):
    data_path = tmp_path / "data_nxbcl"
    runtime_dir = data_path / "runtime"
    state_dir = runtime_dir / "state"
    tmp_dir = data_path / "tmp"
    logs_dir = data_path / "logs"
    chall_dir = data_path / "chall"
    db_file = data_path / "nxbcl.db"

    for path in (state_dir, tmp_dir, logs_dir, chall_dir):
        path.mkdir(parents=True, exist_ok=True)
    (state_dir / "nxbcl.pid").write_text("1234\n", encoding="utf-8")
    (state_dir / "rpc_state.json").write_text("{}", encoding="utf-8")
    (tmp_dir / "scratch.txt").write_text("temp", encoding="utf-8")
    (logs_dir / "nxbcl.log").write_text("log", encoding="utf-8")
    db_file.write_text("sqlite", encoding="utf-8")
    db_file.with_name(db_file.name + "-wal").write_text("wal", encoding="utf-8")

    config = SimpleNamespace(
        state_dir=state_dir,
        tmp_dir=tmp_dir,
        logs_dir=logs_dir,
        db_file=db_file,
    )
    monkeypatch.setattr(cli_main, "get_nxbcl_config", lambda: config)

    removed = cli_main.cleanup_runtime_artifacts()

    assert runtime_dir.exists() is False
    assert tmp_dir.exists() is False
    assert logs_dir.exists() is False
    assert db_file.exists() is False
    assert db_file.with_name(db_file.name + "-wal").exists() is False
    assert chall_dir.exists() is True
    assert removed


def test_build_parser_includes_lifecycle_commands():
    parser = cli_main.build_parser()

    assert parser.parse_args(["up"]).command == "up"
    assert parser.parse_args(["down"]).command == "down"
    assert parser.parse_args(["ps"]).command == "ps"
    assert parser.parse_args(["ps", "--kill"]).kill is True
    assert parser.parse_args(["ps-kill"]).command == "ps-kill"
