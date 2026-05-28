import logging
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Response, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.app.utils.config import get_nxbcl_config
from src.app.utils.db import get_db_conn
from src.app.services.session import SessionService, utc_now
from src.app.services.pow import PowService
from src.app.services.registry import ChallengeRegistry
from src.app.services.adapter import NxctlAdapter

logger = logging.getLogger(__name__)

app = FastAPI(title="NXBCL Blockchain Challenge Launcher")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Load configuration
config = get_nxbcl_config()
rpc_state_file = config.state_dir / "rpc_state.json"


def resolve_public_url(configured_url: str, fallback_url: str) -> str:
    configured_url = (configured_url or "").strip().rstrip("/")
    if configured_url:
        return configured_url
    return fallback_url


def load_rpc_state() -> Optional[datetime]:
    global rpc_expires_at
    if rpc_expires_at:
        return rpc_expires_at
    if not rpc_state_file.exists():
        return None
    try:
        payload = json.loads(rpc_state_file.read_text(encoding="utf-8"))
        expires_at = payload.get("expires_at")
        if expires_at:
            rpc_expires_at = datetime.fromisoformat(expires_at)
    except Exception:
        rpc_expires_at = None
    return rpc_expires_at


def save_rpc_state(expires_at: Optional[datetime]) -> None:
    rpc_state_file.parent.mkdir(parents=True, exist_ok=True)
    if not expires_at:
        if rpc_state_file.exists():
            try:
                rpc_state_file.unlink()
            except Exception:
                pass
        return

    rpc_state_file.write_text(
        json.dumps({"expires_at": expires_at.isoformat()}),
        encoding="utf-8",
    )

# Mount static folder if it exists
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="frontend not built; run `cd nxbcl/src/frontend && npm install && npm run build`",
        )
    return FileResponse(index_path)

# Request schemas
class ChallengeReq(BaseModel):
    user_id: Optional[str] = None

class SolutionReq(BaseModel):
    challenge_token: str
    solution: str
    user_id: Optional[str] = None

# Helper dependency to resolve user_id from headers
def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(status_code=401, detail="missing X-User-Id header")
    return x_user_id.strip()

# Dependency to check/get active session
async def get_session(
    request: Request,
    challenge_id: str,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None)
) -> Dict[str, Any]:
    session_id = request.cookies.get("nxbc_session")
    if not session_id and authorization and authorization.startswith("Bearer "):
        session_id = authorization[7:]

    if not session_id:
        raise HTTPException(status_code=401, detail="missing session token")

    session_service = SessionService(config.db_file, config.session_ttl_seconds)
    session = session_service.validate_session(session_id, challenge_id)
    if not session:
        raise HTTPException(status_code=401, detail="invalid or expired session")

    if x_user_id and x_user_id != session["user_id"]:
        raise HTTPException(status_code=403, detail="user mismatch")

    return session

@app.get("/api/health")
def api_health():
    return {"status": "ok"}

@app.get("/api/challenges")
def api_list_challenges():
    fallback_dir = PROJECT_ROOT / "challenges"
    registry = ChallengeRegistry(config.chall_dir, fallback_dir)
    return registry.list_challenges()

@app.post("/api/challenges/{challenge_id}/pow/challenge")
def api_issue_pow(
    challenge_id: str,
    req: Optional[ChallengeReq] = None,
    x_user_id: Optional[str] = Header(None)
):
    user_id = None
    if req:
        user_id = req.user_id
    if not user_id:
        user_id = x_user_id

    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required either in request body or via X-User-Id header")

    pow_service = PowService(config.db_file, config.pow_zero_prefix, 120)
    challenge = pow_service.issue_challenge(user_id.strip(), challenge_id)
    return challenge

@app.post("/api/challenges/{challenge_id}/pow/solution")
def api_verify_pow(
    challenge_id: str,
    req: SolutionReq,
    response: Response,
    x_user_id: Optional[str] = Header(None)
):
    user_id = req.user_id or x_user_id
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    user_id = user_id.strip()
    pow_service = PowService(config.db_file, config.pow_zero_prefix, 120)
    verified = pow_service.verify_solution(user_id, challenge_id, req.challenge_token, req.solution)

    if not verified:
        raise HTTPException(status_code=400, detail="invalid solution or expired/reused token")

    # Generate session
    session_service = SessionService(config.db_file, config.session_ttl_seconds)
    session_id = session_service.create_session(user_id, challenge_id)

    # Set Cookie
    response.set_cookie(
        key="nxbc_session",
        value=session_id,
        max_age=config.session_ttl_seconds,
        httponly=True,
        samesite="lax"
    )

    return {
        "status": "success",
        "session_id": session_id,
        "expires_in": config.session_ttl_seconds
    }

def sweep_expired_instances(conn):
    conn.execute(
        """
        DELETE FROM instances
        WHERE status = 'running' AND expires_at <= ?
        """,
        (utc_now().isoformat(),)
    )

def get_running_instances_count() -> int:
    with get_db_conn(config.db_file) as conn:
        sweep_expired_instances(conn)
        row = conn.execute(
            "SELECT COUNT(*) as count FROM instances WHERE status = 'running'"
        ).fetchone()
        return row["count"] if row else 0

def instance_response(instance: Dict[str, Any], chall_desc: Dict[str, Any]) -> Dict[str, Any]:
    response = dict(instance)
    response.setdefault("setup_address", response.get("deploy_address"))
    response.setdefault(
        "rpc_url",
        resolve_public_url(
            config.rpc_base_url,
            f"http://localhost:{response.get('rpc_port', 8545)}",
        ),
    )
    response.setdefault("chain_id", chall_desc.get("chain_id", 31337))
    response["extend_threshold_seconds"] = config.challenge_extend_threshold_seconds
    response["extend_seconds"] = config.challenge_extend_seconds
    return response

@app.post("/api/challenges/{challenge_id}/start")
def api_start_challenge(
    challenge_id: str,
    restart: bool = False,
    session: Dict[str, Any] = Depends(get_session)
):
    # Verify if challenge actually exists
    fallback_dir = PROJECT_ROOT / "challenges"
    registry = ChallengeRegistry(config.chall_dir, fallback_dir)
    chall_desc = registry.get_challenge(challenge_id)
    if not chall_desc:
        raise HTTPException(status_code=404, detail="challenge not found")

    session_id = session["session_id"]

    with get_db_conn(config.db_file) as conn:
        sweep_expired_instances(conn)

    # If not restart, check if we already have an active running instance for this session
    if not restart:
        with get_db_conn(config.db_file) as conn:
            row = conn.execute(
                """
                SELECT instance_id, wallet_address, private_key, deploy_address, rpc_port, status, expires_at
                FROM instances
                WHERE session_id = ? AND challenge_id = ? AND status = 'running'
                """,
                (session_id, challenge_id)
            ).fetchone()

            if row:
                # Idempotent response: return existing running instance
                return instance_response(dict(row), chall_desc)

    # Remove any previous instance records owned by this user so only one challenge context remains.
    with get_db_conn(config.db_file) as conn:
        session_rows = conn.execute(
            "SELECT session_id FROM sessions WHERE user_id = ?",
            (session["user_id"],)
        ).fetchall()
        user_sessions = [r["session_id"] for r in session_rows]

        if user_sessions:
            placeholders = ",".join("?" for _ in user_sessions)
            conn.execute(
                f"""
                UPDATE instances
                SET status = 'stopped'
                WHERE session_id IN ({placeholders}) AND status = 'running'
                """,
                user_sessions
            )
            conn.execute(
                f"DELETE FROM instances WHERE session_id IN ({placeholders})",
                user_sessions
            )

    # No concurrency limits needed for shared_chain scope

    # Start new instance using adapter stub
    adapter = NxctlAdapter(config.data_path)
    try:
        inst = adapter.start_instance(session_id, challenge_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    expires_at = utc_now() + timedelta(seconds=config.challenge_ttl_seconds)

    with get_db_conn(config.db_file) as conn:
        conn.execute(
            """
            INSERT INTO instances (instance_id, session_id, challenge_id, wallet_address, private_key, deploy_address, rpc_port, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inst["instance_id"],
                session_id,
                challenge_id,
                inst["wallet_address"],
                inst["private_key"],
                inst["deploy_address"],
                inst["rpc_port"],
                inst["status"],
                utc_now().isoformat(),
                expires_at.isoformat()
            )
        )

    return instance_response({
        "instance_id": inst["instance_id"],
        "wallet_address": inst["wallet_address"],
        "private_key": inst["private_key"],
        "deploy_address": inst["deploy_address"],
        "setup_address": inst.get("setup_address", inst["deploy_address"]),
        "rpc_url": resolve_public_url(
            config.rpc_base_url,
            inst.get("rpc_url", f"http://localhost:{inst['rpc_port']}"),
        ),
        "rpc_port": inst["rpc_port"],
        "chain_id": inst.get("chain_id", chall_desc.get("chain_id", 31337)),
        "status": inst["status"],
        "expires_at": expires_at.isoformat()
    }, chall_desc)

# Also support explicit POST /api/challenges/{id}/restart path
@app.post("/api/challenges/{challenge_id}/restart")
def api_restart_challenge(
    challenge_id: str,
    session: Dict[str, Any] = Depends(get_session)
):
    return api_start_challenge(challenge_id=challenge_id, restart=True, session=session)

@app.get("/api/challenges/{challenge_id}/instance")
def api_get_instance(
    challenge_id: str,
    session: Dict[str, Any] = Depends(get_session)
):
    fallback_dir = PROJECT_ROOT / "challenges"
    registry = ChallengeRegistry(config.chall_dir, fallback_dir)
    chall_desc = registry.get_challenge(challenge_id)
    if not chall_desc:
        raise HTTPException(status_code=404, detail="challenge not found")

    session_id = session["session_id"]
    with get_db_conn(config.db_file) as conn:
        sweep_expired_instances(conn)
        row = conn.execute(
            """
            SELECT instance_id, wallet_address, private_key, deploy_address, rpc_port, status, expires_at
            FROM instances
            WHERE session_id = ? AND challenge_id = ? AND status = 'running'
            """,
            (session_id, challenge_id)
        ).fetchone()

        if row:
            return instance_response(dict(row), chall_desc)

    raise HTTPException(status_code=404, detail="no active instance found")

@app.post("/api/challenges/{challenge_id}/extend")
def api_extend_challenge(
    challenge_id: str,
    session: Dict[str, Any] = Depends(get_session)
):
    session_id = session["session_id"]
    with get_db_conn(config.db_file) as conn:
        sweep_expired_instances(conn)
        row = conn.execute(
            """
            SELECT instance_id, expires_at, created_at
            FROM instances
            WHERE session_id = ? AND challenge_id = ? AND status = 'running'
            """,
            (session_id, challenge_id)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="no active running instance found to extend")

        now = utc_now()
        expires_at = datetime.fromisoformat(row["expires_at"])
        created_at = datetime.fromisoformat(row["created_at"])

        remaining_seconds = (expires_at - now).total_seconds()
        elapsed_seconds = (now - created_at).total_seconds()

        # Enforce cooldown / wait limit configured in config.yml
        if remaining_seconds > config.challenge_extend_threshold_seconds:
            minutes_to_wait = int((remaining_seconds - config.challenge_extend_threshold_seconds) / 60) + 1
            raise HTTPException(
                status_code=400,
                detail=f"You can only extend the instance when there are less than {int(config.challenge_extend_threshold_seconds / 60)} minutes remaining (please wait {minutes_to_wait} more minute(s))"
            )

        new_expires_at = expires_at + timedelta(seconds=config.challenge_extend_seconds)

        conn.execute(
            """
            UPDATE instances
            SET expires_at = ?
            WHERE session_id = ? AND challenge_id = ? AND status = 'running'
            """,
            (new_expires_at.isoformat(), session_id, challenge_id)
        )

        return {
            "status": "success",
            "expires_at": new_expires_at.isoformat(),
            "expires_in": max(0, int((new_expires_at - now).total_seconds()))
        }

@app.post("/api/challenges/{challenge_id}/check")
def api_check_challenge(
    challenge_id: str,
    session: Dict[str, Any] = Depends(get_session)
):
    fallback_dir = PROJECT_ROOT / "challenges"
    registry = ChallengeRegistry(config.chall_dir, fallback_dir)
    chall_desc = registry.get_challenge(challenge_id)
    if not chall_desc:
        raise HTTPException(status_code=404, detail="challenge not found")

    session_id = session["session_id"]
    with get_db_conn(config.db_file) as conn:
        sweep_expired_instances(conn)
        row = conn.execute(
            """
            SELECT instance_id, wallet_address, private_key, deploy_address, rpc_port, expires_at
            FROM instances
            WHERE session_id = ? AND challenge_id = ? AND status = 'running'
            """,
            (session_id, challenge_id)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="No active instance found for this challenge")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= utc_now():
            raise HTTPException(status_code=410, detail="Challenge instance has expired")

        setup_address = row["deploy_address"]

        solved = False
        try:
            from web3 import Web3
            local_rpc = "http://127.0.0.1:8545"
            w3 = Web3(Web3.HTTPProvider(local_rpc))
            if not w3.is_connected():
                w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))

            if w3.is_connected():
                try:
                    setup_abi = [
                        {
                            "inputs": [],
                            "name": "isSolved",
                            "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                            "stateMutability": "view",
                            "type": "function",
                        }
                    ]
                    setup = w3.eth.contract(address=w3.to_checksum_address(setup_address), abi=setup_abi)
                    solved = bool(setup.functions.isSolved().call())
                except Exception as e:
                    logger.warning(f"Failed to check isSolved via web3: {e}")
        except ImportError:
            pass

        if solved:
            conn.execute(
                """
                INSERT INTO solves (user_id, challenge_id, solved, solved_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, challenge_id) DO UPDATE SET solved = 1, solved_at = ?
                """,
                (session["user_id"], challenge_id, utc_now().isoformat(), utc_now().isoformat())
            )

        # Dynamic flag resolution:
        # 1. Check environment variable specifically for this challenge: e.g. FLAG_01_CONVERGENCE_SEED or FLAG_02_CONVERGENCE
        env_var_name = f"FLAG_{challenge_id.replace('-', '_').upper()}"
        flag = os.getenv(env_var_name)

        # Load registry and config
        fallback_dir = PROJECT_ROOT / "challenges"
        registry = ChallengeRegistry(config.chall_dir, fallback_dir)
        chall_config = registry.get_challenge(challenge_id)

        # 2. Check if a flag.txt file exists in the challenge folder
        if not flag and chall_config:
            for base in [config.chall_dir, fallback_dir]:
                # Try direct subfolder
                flag_file = base / challenge_id / "flag.txt"
                if flag_file.exists():
                    try:
                        flag = flag_file.read_text(encoding="utf-8").strip()
                        break
                    except Exception:
                        pass
                # Try under challenges subfolder
                flag_file_nested = base / "challenges" / challenge_id / "flag.txt"
                if flag_file_nested.exists():
                    try:
                        flag = flag_file_nested.read_text(encoding="utf-8").strip()
                        break
                    except Exception:
                        pass

        # 3. Check if there is a 'flag' field in challenge.yml
        if not flag and chall_config:
            flag = chall_config.get("flag")

        # 4. Fallback to standard global FLAG env variable or fallback placeholder
        if not flag:
            flag = os.getenv("FLAG", f"TCP1P{{{challenge_id.replace('-', '_')}_solved_abc123}}")

        return {
            "solved": solved,
            "flag": flag if solved else None,
            "message": "Challenge solved! Here is your flag." if solved else "Not solved yet. Keep trying!"
        }

@app.get("/api/instances/active")
def api_get_active_instances(
    x_user_id: Optional[str] = Header(None)
):
    with get_db_conn(config.db_file) as conn:
        sweep_expired_instances(conn)
        row = conn.execute(
            """
            SELECT challenge_id, instance_id, expires_at, status
            FROM instances
            WHERE status = 'running'
            ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()

        if row:
            return {
                "active": True,
                "challenge_id": row["challenge_id"],
                "expires_at": row["expires_at"],
                "status": row["status"]
            }

rpc_expires_at: Optional[datetime] = None

def is_rpc_reachable() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 8545), timeout=1.0):
            return True
    except Exception:
        try:
            with socket.create_connection(("localhost", 8545), timeout=1.0):
                return True
        except Exception:
            return False

@app.get("/api/rpc/status")
def api_rpc_status():
    global rpc_expires_at
    load_rpc_state()
    now = datetime.now(timezone.utc)

    if rpc_expires_at and now >= rpc_expires_at:
        try:
            import subprocess
            import os
            subprocess.run(
                ["docker", "compose", "down", "-v", "--remove-orphans"],
                cwd=str(config.chall_dir),
                shell=(os.name == "nt"),
                capture_output=True,
                text=True,
            )
        except Exception:
            pass
        # Clear the database when RPC TTL expires
        try:
            with get_db_conn(config.db_file) as conn:
                conn.execute("DELETE FROM instances")
                conn.commit()
        except Exception:
            pass
        rpc_expires_at = None
        save_rpc_state(None)

    connected = rpc_expires_at is not None and now < rpc_expires_at
    if connected and not is_rpc_reachable():
        connected = False

    if not connected:
        try:
            with get_db_conn(config.db_file) as conn:
                conn.execute("DELETE FROM instances")
                conn.commit()
        except Exception:
            pass
        rpc_expires_at = None
        save_rpc_state(None)
    return {
        "status": "running" if connected else "stopped",
        "rpc_url": resolve_public_url(config.rpc_base_url, "http://localhost:8545"),
        "expires_at": rpc_expires_at.isoformat() if rpc_expires_at else None,
        "extend_threshold_seconds": config.rpc_extend_threshold_seconds,
        "extend_seconds": config.rpc_extend_seconds
    }
@app.post("/api/rpc/start")
def api_rpc_start():
    import subprocess
    import os
    chall_dir = config.chall_dir
    if not chall_dir.exists():
        raise HTTPException(status_code=400, detail="Challenge directory not initialized")
    try:
        res = subprocess.run(
            ["docker", "compose", "up", "-d", "anvil", "rpc"],
            cwd=str(chall_dir),
            shell=(os.name == "nt"),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            return {"status": "failed", "error": res.stderr}

        global rpc_expires_at
        rpc_expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.rpc_ttl_seconds)
        save_rpc_state(rpc_expires_at)
        return {
            "status": "success",
            "expires_at": rpc_expires_at.isoformat(),
            "extend_threshold_seconds": config.rpc_extend_threshold_seconds,
            "extend_seconds": config.rpc_extend_seconds,
            "rpc_url": resolve_public_url(config.rpc_base_url, "http://localhost:8545"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rpc/restart")
def api_rpc_restart():
    import subprocess
    import os
    chall_dir = config.chall_dir
    if not chall_dir.exists():
        raise HTTPException(status_code=400, detail="Challenge directory not initialized")
    try:
        # Stop — this wipes chain state (volumes), so all existing instances are invalid
        subprocess.run(
            ["docker", "compose", "down", "-v", "--remove-orphans"],
            cwd=str(chall_dir),
            shell=(os.name == "nt"),
            capture_output=True,
            text=True
        )

        # Purge all instance records — chain state is destroyed, old credentials are stale
        with get_db_conn(config.db_file) as conn:
            conn.execute("DELETE FROM instances WHERE status = 'running'")
            logger.info("Purged all running instance records after RPC restart (chain state wiped)")

        # Start
        res = subprocess.run(
            ["docker", "compose", "up", "-d", "anvil", "rpc"],
            cwd=str(chall_dir),
            shell=(os.name == "nt"),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            return {"status": "failed", "error": res.stderr}

        global rpc_expires_at
        rpc_expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.rpc_ttl_seconds)
        save_rpc_state(rpc_expires_at)
        return {
            "status": "success",
            "expires_at": rpc_expires_at.isoformat(),
            "extend_threshold_seconds": config.rpc_extend_threshold_seconds,
            "extend_seconds": config.rpc_extend_seconds,
            "rpc_url": resolve_public_url(config.rpc_base_url, "http://localhost:8545"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rpc/stop")
def api_rpc_stop():
    import subprocess
    import os
    chall_dir = config.chall_dir
    if not chall_dir.exists():
        raise HTTPException(status_code=400, detail="Challenge directory not initialized")
    try:
        subprocess.run(
            ["docker", "compose", "down", "-v", "--remove-orphans"],
            cwd=str(chall_dir),
            shell=(os.name == "nt"),
            capture_output=True,
            text=True
        )
        # Purge all instance records — chain is down, credentials are invalid
        with get_db_conn(config.db_file) as conn:
            conn.execute("DELETE FROM instances WHERE status = 'running'")
            logger.info("Purged all running instance records after RPC stop")

        global rpc_expires_at
        rpc_expires_at = None
        save_rpc_state(None)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/services")
def api_services():
    """Return a compact view of key services: anvil (RPC), panel/API, and active instances."""
    load_rpc_state()
    now = datetime.now(timezone.utc)
    anvil_running = rpc_expires_at is not None and now < rpc_expires_at

    active_instances = []
    try:
        with get_db_conn(config.db_file) as conn:
            sweep_expired_instances(conn)
            rows = conn.execute(
                "SELECT challenge_id, instance_id, wallet_address, rpc_port, expires_at, status FROM instances WHERE status = 'running' ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            for r in rows:
                active_instances.append({
                    "challenge_id": r["challenge_id"],
                    "instance_id": r["instance_id"],
                    "wallet_address": r["wallet_address"],
                    "rpc_port": r["rpc_port"],
                    "expires_at": r["expires_at"],
                    "status": r["status"],
                })
    except Exception:
        active_instances = []

    return {
        "anvil": {
            "status": "running" if anvil_running else "stopped",
            "rpc_url": resolve_public_url(config.rpc_base_url, "http://localhost:8545"),
            "expires_at": rpc_expires_at.isoformat() if rpc_expires_at else None,
        },
        "panel": {"status": "running"},
        "active_instances": active_instances,
    }

@app.post("/api/rpc/extend")
def api_rpc_extend():
    global rpc_expires_at
    load_rpc_state()
    if not rpc_expires_at:
        raise HTTPException(status_code=400, detail="RPC Node is not running")

    now = datetime.now(timezone.utc)
    remaining_seconds = (rpc_expires_at - now).total_seconds()
    if remaining_seconds > config.rpc_extend_threshold_seconds:
        minutes_to_wait = int((remaining_seconds - config.rpc_extend_threshold_seconds) / 60) + 1
        raise HTTPException(
            status_code=400,
            detail=f"You can only extend RPC when under {int(config.rpc_extend_threshold_seconds / 60)} minutes remaining (please wait {minutes_to_wait} more minute(s))"
        )

    rpc_expires_at += timedelta(seconds=config.rpc_extend_seconds)
    save_rpc_state(rpc_expires_at)
    return {
        "status": "success",
        "expires_at": rpc_expires_at.isoformat()
    }
