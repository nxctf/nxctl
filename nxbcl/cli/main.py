import argparse
import subprocess
import sys
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
