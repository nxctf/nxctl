import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nxbcl.cli.sync import sync
from nxbcl.launcher.challenges.registry import ChallengeRegistry
from nxbcl.launcher.config import get_nxbcl_config
from nxbcl.launcher.db.connection import init_db


FRONTEND_DIR = PROJECT_ROOT / "nxbcl" / "frontend"
COMPOSE_SERVICES = ("anvil", "rpc")


def ensure_runtime_dirs() -> None:
    config = get_nxbcl_config()
    for path in (
        config.data_path,
        config.chall_dir,
        config.locks_dir,
        config.state_dir,
        config.tmp_dir,
        config.logs_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    init_db(config.db_file)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def remove_sqlite_artifacts(db_file: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        remove_path(db_file.with_name(db_file.name + suffix))


def cleanup_runtime_artifacts() -> list[Path]:
    config = get_nxbcl_config()
    removed: list[Path] = []

    for path in (config.state_dir.parent, config.tmp_dir, config.logs_dir):
        if path.exists():
            remove_path(path)
            removed.append(path)

    if config.db_file.exists() or any(
        config.db_file.with_name(config.db_file.name + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        remove_sqlite_artifacts(config.db_file)
        removed.append(config.db_file)

    return removed


def rpc_state_file() -> Path:
    return get_nxbcl_config().state_dir / "rpc_state.json"


def load_rpc_expires_at() -> datetime | None:
    state_file = rpc_state_file()
    if not state_file.exists():
        return None
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        expires_at = payload.get("expires_at")
        if not expires_at:
            return None
        return datetime.fromisoformat(expires_at)
    except Exception:
        return None


def save_rpc_state(expires_at: datetime | None) -> None:
    state_file = rpc_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if not expires_at:
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass
        return

    state_file.write_text(
        json.dumps({"expires_at": expires_at.isoformat()}),
        encoding="utf-8",
    )


def seed_rpc_state() -> datetime:
    config = get_nxbcl_config()
    current_expires_at = load_rpc_expires_at()
    if current_expires_at and current_expires_at > datetime.now(timezone.utc):
        return current_expires_at

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.rpc_ttl_seconds)
    save_rpc_state(expires_at)
    return expires_at


def compose_challenge_dir() -> Path:
    return get_nxbcl_config().chall_dir


def run_compose_command(arguments: list[str]) -> subprocess.CompletedProcess[str] | None:
    compose_dir = compose_challenge_dir()
    if not compose_dir.exists():
        print(f"compose directory not found: {compose_dir}", file=sys.stderr)
        print("Run `nxbcl sync` first.", file=sys.stderr)
        return None

    try:
        return subprocess.run(
            ["docker", "compose", *arguments],
            cwd=str(compose_dir),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("docker is not installed or not available in PATH", file=sys.stderr)
        return None


def cmd_init_db(_args: argparse.Namespace) -> int:
    config = get_nxbcl_config()
    ensure_runtime_dirs()
    print("NXBCL initialized")
    print(f"data_dir:  {config.data_path}")
    print(f"db_file:   {config.db_file}")
    print(f"chall_dir: {config.chall_dir}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    if not args.dry_run:
        ensure_runtime_dirs()
    return sync(dry_run=args.dry_run)


def cmd_challenges(_args: argparse.Namespace) -> int:
    config = get_nxbcl_config()
    fallback_dir = PROJECT_ROOT / "nxbcl" / "challenges"
    registry = ChallengeRegistry(config.chall_dir, fallback_dir)

    challenges = registry.list_challenges()
    if not challenges:
        print("No challenges found.")
        return 0

    for challenge in challenges:
        challenge_id = challenge.get("id", "")
        name = challenge.get("name", "")
        kind = challenge.get("kind", "unknown")
        print(f"{challenge_id}\t{kind}\t{name}")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    config = get_nxbcl_config()
    print("NXBCL doctor")
    print(f"enabled:   {config.enabled}")
    print(f"data_dir:  {config.data_path}")
    print(f"db_file:   {config.db_file} ({'exists' if config.db_file.exists() else 'missing'})")
    print(f"chall_dir: {config.chall_dir} ({'exists' if config.chall_dir.exists() else 'missing'})")
    print(f"git_repo:  {config.git_repo or '(not configured)'}")
    print(f"branch:    {config.git_branch}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Run: bash nxbcl/setup.sh install", file=sys.stderr)
        return 1

    uvicorn.run(
        "nxbcl.launcher.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_up(_args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    result = run_compose_command(["up", "-d", *COMPOSE_SERVICES])
    if result is None:
        return 1
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return result.returncode

    print("NXBCL compose stack started")
    expires_at = seed_rpc_state()
    remaining_minutes = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds() / 60))
    print(f"RPC lease expires at {expires_at.isoformat()} ({remaining_minutes} minute(s) left)")
    if result.stdout:
        print(result.stdout, end="")
    return 0


def cmd_down(_args: argparse.Namespace) -> int:
    result = run_compose_command(["down", "--remove-orphans"])
    if result is None:
        return 1
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return result.returncode

    print("NXBCL compose stack stopped")
    save_rpc_state(None)
    if result.stdout:
        print(result.stdout, end="")
    return 0


def cmd_ps(args: argparse.Namespace) -> int:
    result = run_compose_command(["ps"])
    if result is None:
        return 1

    exit_code = result.returncode
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    expires_at = load_rpc_expires_at()
    if expires_at:
        remaining_seconds = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        print(f"RPC lease: {minutes}:{seconds:02d} remaining")
    else:
        print("RPC lease: unavailable")

    if args.kill:
        kill_result = run_compose_command(["down", "-v", "--remove-orphans"])
        if kill_result is None:
            return 1
        if kill_result.returncode != 0:
            if kill_result.stdout:
                print(kill_result.stdout, end="")
            if kill_result.stderr:
                print(kill_result.stderr, end="", file=sys.stderr)
            return kill_result.returncode

        removed = cleanup_runtime_artifacts()
        save_rpc_state(None)
        if removed:
            print("Removed runtime data:")
            for path in removed:
                print(f"- {path}")
        else:
            print("No runtime data to remove")
        exit_code = kill_result.returncode

    return exit_code


def run_frontend_command(args: list[str]) -> int:
    if not FRONTEND_DIR.exists():
        print(f"frontend directory not found: {FRONTEND_DIR}", file=sys.stderr)
        return 1

    import os
    try:
        result = subprocess.run(args, cwd=str(FRONTEND_DIR), check=False, shell=(os.name == "nt"))
    except FileNotFoundError:
        print("npm is not installed or not available in PATH", file=sys.stderr)
        return 1

    return result.returncode


def cmd_frontend_install(_args: argparse.Namespace) -> int:
    return run_frontend_command(["npm", "install"])


def cmd_frontend_build(_args: argparse.Namespace) -> int:
    return run_frontend_command(["npm", "run", "build"])


def cmd_frontend_dev(_args: argparse.Namespace) -> int:
    return run_frontend_command(["npm", "run", "dev"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nxbcl", description="NXBCL launcher CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-db", help="Create data directories and SQLite schema")
    init_parser.set_defaults(func=cmd_init_db)

    sync_parser = subparsers.add_parser("sync", help="Sync challenge repo into data_nxbcl/chall")
    sync_parser.add_argument("--dry-run", action="store_true", help="Print sync target without cloning")
    sync_parser.set_defaults(func=cmd_sync)

    challenges_parser = subparsers.add_parser("challenges", help="List discovered blockchain challenges")
    challenges_parser.set_defaults(func=cmd_challenges)

    doctor_parser = subparsers.add_parser("doctor", help="Print NXBCL config and data paths")
    doctor_parser.set_defaults(func=cmd_doctor)

    serve_parser = subparsers.add_parser("serve", help="Run the NXBCL FastAPI launcher")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", default=8080, type=int, help="Bind port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")
    serve_parser.set_defaults(func=cmd_serve)

    up_parser = subparsers.add_parser("up", help="Start the compose stack in data_nxbcl/chall")
    up_parser.set_defaults(func=cmd_up)

    down_parser = subparsers.add_parser("down", help="Stop the compose stack in data_nxbcl/chall")
    down_parser.set_defaults(func=cmd_down)

    ps_parser = subparsers.add_parser("ps", help="Show compose stack status")
    ps_parser.add_argument("--kill", action="store_true", help="Stop compose and purge runtime state")
    ps_parser.set_defaults(func=cmd_ps)

    ps_kill_parser = subparsers.add_parser("ps-kill", help="Show compose status and purge runtime state")
    ps_kill_parser.set_defaults(func=lambda _args: cmd_ps(argparse.Namespace(kill=True)))

    frontend_install_parser = subparsers.add_parser("frontend-install", help="Install Vue/Vite frontend dependencies")
    frontend_install_parser.set_defaults(func=cmd_frontend_install)

    frontend_build_parser = subparsers.add_parser("frontend-build", help="Build frontend into nxbcl/launcher/static")
    frontend_build_parser.set_defaults(func=cmd_frontend_build)

    frontend_dev_parser = subparsers.add_parser("frontend-dev", help="Run Vite dev server for the frontend")
    frontend_dev_parser.set_defaults(func=cmd_frontend_dev)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
