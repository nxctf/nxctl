import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Response, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nxbcl.launcher.config import get_nxbcl_config
from nxbcl.launcher.db.connection import get_db_conn
from nxbcl.launcher.auth.session import SessionService, utc_now
from nxbcl.launcher.pow.service import PowService
from nxbcl.launcher.challenges.registry import ChallengeRegistry
from nxbcl.launcher.runtime.adapter import NxctlAdapter

app = FastAPI(title="NXBCL Blockchain Challenge Launcher")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Load configuration
config = get_nxbcl_config()

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
            detail="frontend not built; run `cd nxbcl/frontend && npm install && npm run build`",
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
    fallback_dir = Path(__file__).resolve().parent.parent / "challenges"
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

def get_running_instances_count() -> int:
    with get_db_conn(config.db_file) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM instances WHERE status = 'running'"
        ).fetchone()
        return row["count"] if row else 0

def instance_response(instance: Dict[str, Any], chall_desc: Dict[str, Any]) -> Dict[str, Any]:
    response = dict(instance)
    response.setdefault("setup_address", response.get("deploy_address"))
    response.setdefault("rpc_url", f"http://localhost:{response.get('rpc_port', 8545)}")
    response.setdefault("chain_id", chall_desc.get("chain_id", 31337))
    return response

@app.post("/api/challenges/{challenge_id}/start")
def api_start_challenge(
    challenge_id: str,
    restart: bool = False,
    session: Dict[str, Any] = Depends(get_session)
):
    # Verify if challenge actually exists
    fallback_dir = Path(__file__).resolve().parent.parent / "challenges"
    registry = ChallengeRegistry(config.chall_dir, fallback_dir)
    chall_desc = registry.get_challenge(challenge_id)
    if not chall_desc:
        raise HTTPException(status_code=404, detail="challenge not found")

    session_id = session["session_id"]
    
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

    # Check concurrency limits
    active_count = get_running_instances_count()
    if active_count >= config.max_concurrent:
        raise HTTPException(
            status_code=400,
            detail=f"Too many active challenges running globally (max: {config.max_concurrent})"
        )

    # If restart requested, stop any existing active instance
    with get_db_conn(config.db_file) as conn:
        conn.execute(
            """
            UPDATE instances
            SET status = 'stopped'
            WHERE session_id = ? AND challenge_id = ? AND status = 'running'
            """,
            (session_id, challenge_id)
        )

    # Start new instance using adapter stub
    adapter = NxctlAdapter(config.data_path)
    inst = adapter.start_instance(session_id, challenge_id)
    
    expires_at = utc_now() + timedelta(seconds=config.instance_ttl_seconds)
    
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
        "rpc_url": inst.get("rpc_url", f"http://localhost:{inst['rpc_port']}"),
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
