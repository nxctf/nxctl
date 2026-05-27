import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eth_account import Account
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web3 import Web3


CHALLENGE_ID = os.getenv("CHALLENGE_ID", "04-convergence")
RPC_URL = os.getenv("RPC_URL", "http://anvil:8545")
PUBLIC_RPC_URL = os.getenv("PUBLIC_RPC_URL", "http://localhost:8545")
PORTAL_PUBLIC_URL = os.getenv("PORTAL_PUBLIC_URL", "http://localhost:8080")
METADATA_PATH = Path(os.getenv("METADATA_PATH", "metadata/metadata.json"))
STATE_PATH = Path(os.getenv("STATE_PATH", "metadata/portal_state.json"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
COOKIE_NAME = "nxbc_session"
FLAG = os.getenv("FLAG", "TCP1P{local_flag_not_configured}")
FAUCET_AMOUNT_ETH = os.getenv("FAUCET_AMOUNT_ETH", "0.2")
INSTANCE_TTL_SECONDS = int(os.getenv("INSTANCE_TTL_SECONDS", "1800"))
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
POW_TTL_SECONDS = int(os.getenv("POW_TTL_SECONDS", "120"))
POW_ZERO_PREFIX = os.getenv("POW_ZERO_PREFIX", "000")


FACTORY_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "setupOf",
        "outputs": [{"internalType": "contract Setup", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "player", "type": "address"}],
        "name": "spawnFor",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "player", "type": "address"}],
        "name": "isSolved",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


SETUP_ABI = [
    {
        "inputs": [],
        "name": "challenge",
        "outputs": [{"internalType": "contract Challenge", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "isSolved",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class SolutionRequest(BaseModel):
    challenge_token: str
    solution: str


app = FastAPI(title="NXBC launcher POC for 04-convergence")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_challenge(challenge_id: str) -> None:
    if challenge_id != CHALLENGE_ID:
        raise HTTPException(status_code=404, detail="unknown challenge")


def require_user(x_user_id: str | None) -> str:
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id header")
    return user_id


def normalize_private_key(value: str) -> str:
    return value if value.startswith("0x") else f"0x{value}"


def instance_key(session_id: str, challenge_id: str) -> str:
    return f"{session_id}:{challenge_id}"


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def load_state() -> dict[str, Any]:
    state = load_json(STATE_PATH, {})
    state.setdefault("pow_challenges", {})
    state.setdefault("sessions", {})
    state.setdefault("instances", {})
    state.setdefault("solves", {})
    return state


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_PATH, state)


def load_metadata() -> dict[str, Any]:
    metadata = load_json(METADATA_PATH, {})
    if not metadata.get("factory_address"):
        raise HTTPException(status_code=503, detail="challenge metadata is not ready")
    return metadata


def is_session_active(session: dict[str, Any]) -> bool:
    expires_at = session.get("expires_at")
    if not expires_at:
        return False
    try:
        return parse_iso(expires_at) > utc_now()
    except Exception:
        return False


def create_or_update_session(
    request: Request, response: Response, user_id: str
) -> tuple[str, dict[str, Any]]:
    state = load_state()
    session_id = request.cookies.get(COOKIE_NAME, "")
    session = state["sessions"].get(session_id)

    if (
        not session
        or not is_session_active(session)
        or session.get("user_id") != user_id
    ):
        session_id = secrets.token_urlsafe(32)
        session = {"created_at": now_iso()}

    expires_at = utc_now() + timedelta(seconds=SESSION_TTL_SECONDS)
    session.update(
        {
            "user_id": user_id,
            "updated_at": now_iso(),
            "expires_at": expires_at.isoformat(),
        }
    )
    state["sessions"][session_id] = session
    save_state(state)

    response.set_cookie(
        COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return session_id, session


def pow_digest(prefix: str, solution: str) -> str:
    return hashlib.sha256(f"{prefix}:{solution}".encode("utf-8")).hexdigest()


def create_pow_challenge(user_id: str) -> dict[str, Any]:
    state = load_state()
    token = secrets.token_urlsafe(24)
    prefix = secrets.token_hex(16)
    expires_at = utc_now() + timedelta(seconds=POW_TTL_SECONDS)
    state["pow_challenges"][token] = {
        "user_id": user_id,
        "prefix": prefix,
        "zero_prefix": POW_ZERO_PREFIX,
        "created_at": now_iso(),
        "expires_at": expires_at.isoformat(),
        "used": False,
    }
    save_state(state)
    return {
        "challenge_token": token,
        "prefix": prefix,
        "zero_prefix": POW_ZERO_PREFIX,
        "algorithm": "sha256(prefix + ':' + solution)",
        "expires_in": POW_TTL_SECONDS,
    }


def verify_pow_solution(user_id: str, challenge_token: str, solution: str) -> None:
    state = load_state()
    challenge = state["pow_challenges"].get(challenge_token)
    if not challenge:
        raise HTTPException(status_code=400, detail="challenge not found")
    if challenge.get("used"):
        raise HTTPException(status_code=400, detail="challenge already used")
    if challenge.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="challenge belongs to another user")
    if parse_iso(challenge["expires_at"]) <= utc_now():
        raise HTTPException(status_code=410, detail="challenge expired")

    digest = pow_digest(challenge["prefix"], solution)
    if not digest.startswith(challenge["zero_prefix"]):
        raise HTTPException(status_code=400, detail="invalid challenge solution")

    challenge["used"] = True
    challenge["solved_at"] = now_iso()
    challenge["solution"] = solution
    challenge["digest"] = digest
    state["pow_challenges"][challenge_token] = challenge
    save_state(state)


def require_session(request: Request) -> tuple[str, dict[str, Any]]:
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not session_id:
        raise HTTPException(status_code=401, detail="missing launcher session")

    state = load_state()
    session = state["sessions"].get(session_id)
    if not session or not is_session_active(session):
        raise HTTPException(status_code=401, detail="launcher session expired")

    return session_id, session


def w3() -> Web3:
    client = Web3(Web3.HTTPProvider(RPC_URL))
    if not client.is_connected():
        raise HTTPException(status_code=503, detail="rpc is not reachable")
    return client


def factory_contract(client: Web3):
    metadata = load_metadata()
    factory_address = Web3.to_checksum_address(metadata["factory_address"])
    return client.eth.contract(address=factory_address, abi=FACTORY_ABI)


def setup_contract(client: Web3, setup_address: str):
    return client.eth.contract(
        address=Web3.to_checksum_address(setup_address),
        abi=SETUP_ABI,
    )


def admin_account(client: Web3):
    private_key = os.getenv("FUNDER_PRIVKEY", "").strip()
    if not private_key:
        raise HTTPException(status_code=503, detail="launcher funder is not configured")
    return client.eth.account.from_key(normalize_private_key(private_key))


def send_tx(client: Web3, account, tx: dict[str, Any]):
    tx.setdefault("from", account.address)
    tx.setdefault("nonce", client.eth.get_transaction_count(account.address))
    tx.setdefault("chainId", client.eth.chain_id)
    tx.setdefault("gas", 3_000_000)

    dynamic_fee = (
        "maxFeePerGas" in tx
        or "maxPriorityFeePerGas" in tx
        or tx.get("type") in (2, "0x2")
    )
    if dynamic_fee:
        tx.pop("gasPrice", None)
    else:
        tx.setdefault("gasPrice", client.eth.gas_price)

    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = client.eth.send_raw_transaction(raw)
    receipt = client.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise HTTPException(status_code=500, detail="launcher transaction failed")
    return receipt


def fund_wallet(client: Web3, account, wallet_address: str):
    amount = client.to_wei(FAUCET_AMOUNT_ETH, "ether")
    return send_tx(
        client,
        account,
        {
            "to": wallet_address,
            "value": amount,
            "gas": 21_000,
        },
    )


def spawn_setup(client: Web3, account, wallet_address: str):
    factory = factory_contract(client)
    wallet = Web3.to_checksum_address(wallet_address)
    existing_setup = factory.functions.setupOf(wallet).call()
    if int(existing_setup, 16) != 0:
        return Web3.to_checksum_address(existing_setup), None

    tx = factory.functions.spawnFor(wallet).build_transaction(
        {
            "from": account.address,
            "gas": 3_500_000,
        }
    )
    receipt = send_tx(client, account, tx)
    setup_address = factory.functions.setupOf(wallet).call()
    return Web3.to_checksum_address(setup_address), receipt


def is_instance_active(instance: dict[str, Any]) -> bool:
    expires_at = instance.get("expires_at")
    if not expires_at:
        return False
    try:
        return parse_iso(expires_at) > utc_now()
    except Exception:
        return False


def public_instance_response(instance: dict[str, Any], reused: bool = False) -> dict[str, Any]:
    expires_at = parse_iso(instance["expires_at"])
    expires_in = max(0, int((expires_at - utc_now()).total_seconds()))
    return {
        "challenge_id": instance["challenge_id"],
        "rpc_url": instance["rpc_url"],
        "chain_id": instance["chain_id"],
        "wallet_address": instance["wallet_address"],
        "private_key": instance["private_key"],
        "setup_contract": instance["setup_address"],
        "challenge_contract": instance.get("challenge_address"),
        "factory_address": instance["factory_address"],
        "expires_in": expires_in,
        "reused": reused,
    }


def launch_for_session(
    challenge_id: str, session_id: str, user_id: str
) -> dict[str, Any]:
    require_challenge(challenge_id)
    metadata = load_metadata()
    state = load_state()
    key = instance_key(session_id, challenge_id)
    existing = state["instances"].get(key)
    if existing and is_instance_active(existing):
        return public_instance_response(existing, reused=True)

    client = w3()
    launcher = admin_account(client)
    player = Account.create()
    private_key = normalize_private_key(player.key.hex())
    wallet_address = Web3.to_checksum_address(player.address)

    fund_receipt = fund_wallet(client, launcher, wallet_address)
    setup_address, spawn_receipt = spawn_setup(client, launcher, wallet_address)
    setup = setup_contract(client, setup_address)
    challenge_address = Web3.to_checksum_address(setup.functions.challenge().call())

    created_at = utc_now()
    expires_at = created_at + timedelta(seconds=INSTANCE_TTL_SECONDS)
    instance = {
        "id": key,
        "session_id": session_id,
        "user_id": user_id,
        "challenge_id": challenge_id,
        "rpc_url": metadata.get("rpc_url", PUBLIC_RPC_URL),
        "chain_id": client.eth.chain_id,
        "private_key": private_key,
        "wallet_address": wallet_address,
        "factory_address": Web3.to_checksum_address(metadata["factory_address"]),
        "setup_address": setup_address,
        "challenge_address": challenge_address,
        "fund_tx": fund_receipt.transactionHash.hex(),
        "spawn_tx": spawn_receipt.transactionHash.hex() if spawn_receipt else None,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "solved": False,
    }
    state["instances"][key] = instance
    save_state(state)
    return public_instance_response(instance)


def load_session_instance(challenge_id: str, session_id: str) -> dict[str, Any]:
    require_challenge(challenge_id)
    state = load_state()
    instance = state["instances"].get(instance_key(session_id, challenge_id))
    if not instance:
        raise HTTPException(status_code=400, detail="session has no active instance")
    if not is_instance_active(instance):
        raise HTTPException(status_code=410, detail="instance expired")
    return instance


def check_for_session(challenge_id: str, session_id: str, user_id: str) -> dict[str, Any]:
    instance = load_session_instance(challenge_id, session_id)
    client = w3()
    setup = setup_contract(client, instance["setup_address"])
    solved = bool(setup.functions.isSolved().call())

    if not solved:
        return {
            "user_id": user_id,
            "challenge_id": challenge_id,
            "wallet_address": instance["wallet_address"],
            "setup_contract": instance["setup_address"],
            "solved": False,
        }

    state = load_state()
    key = instance_key(session_id, challenge_id)
    state["instances"][key]["solved"] = True
    state["solves"][key] = {
        "wallet_address": instance["wallet_address"],
        "setup_address": instance["setup_address"],
        "solved_at": now_iso(),
    }
    save_state(state)

    return {
        "user_id": user_id,
        "challenge_id": challenge_id,
        "wallet_address": instance["wallet_address"],
        "setup_contract": instance["setup_address"],
        "solved": True,
        "flag": FLAG,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api")
def api_index():
    return {
        "service": "NXBC launcher POC for 04-convergence",
        "challenge_id": CHALLENGE_ID,
        "portal_url": PORTAL_PUBLIC_URL,
        "routes": [
            "POST /challenge",
            "POST /solution",
            f"POST /launch/{CHALLENGE_ID}",
            f"POST /check/{CHALLENGE_ID}",
            f"GET /data/{CHALLENGE_ID}",
            f"POST /api/challenges/{CHALLENGE_ID}/launch",
            f"POST /api/challenges/{CHALLENGE_ID}/check",
        ],
    }


@app.post("/challenge")
@app.post("/api/challenge")
def challenge_gate(x_user_id: str | None = Header(default=None)):
    user_id = require_user(x_user_id)
    return create_pow_challenge(user_id)


@app.post("/solution")
@app.post("/api/solution")
def solve_challenge_gate(
    request: Request,
    response: Response,
    body: SolutionRequest,
    x_user_id: str | None = Header(default=None),
):
    user_id = require_user(x_user_id)
    verify_pow_solution(user_id, body.challenge_token, body.solution)
    _, session = create_or_update_session(request, response, user_id)
    return {
        "user_id": user_id,
        "session": "active",
        "expires_at": session["expires_at"],
    }


@app.post("/session")
@app.post("/api/session")
def create_session_disabled():
    raise HTTPException(
        status_code=410,
        detail="direct session creation is disabled; use /challenge and /solution",
    )


@app.get("/health")
def health():
    client = w3()
    return {
        "ok": True,
        "chain_id": client.eth.chain_id,
        "metadata_ready": METADATA_PATH.exists(),
    }


@app.get("/api/challenges/{challenge_id}")
def challenge(challenge_id: str, request: Request):
    require_challenge(challenge_id)
    metadata = load_metadata()
    instance = None
    session_id = request.cookies.get(COOKIE_NAME, "")
    if session_id:
        state = load_state()
        record = state["instances"].get(instance_key(session_id, challenge_id))
        if record and is_instance_active(record):
            instance = {
                "wallet_address": record["wallet_address"],
                "setup_contract": record["setup_address"],
                "expires_at": record["expires_at"],
                "solved": record.get("solved", False),
            }

    return {
        "challenge_id": challenge_id,
        "kind": "blockchain_rpc",
        "protocol": "http",
        "chain_family": "evm",
        "chain_id": metadata.get("chain_id", 31337),
        "rpc_url": metadata.get("rpc_url", PUBLIC_RPC_URL),
        "factory_address": metadata["factory_address"],
        "spawn_function": "spawnFor(address)",
        "checker": "Setup.isSolved()",
        "isolation_scope": "shared_chain_per_user_setup",
        "instance": instance,
    }


@app.post("/launch/{challenge_id}")
@app.post("/api/challenges/{challenge_id}/launch")
def launch(challenge_id: str, request: Request):
    session_id, session = require_session(request)
    return launch_for_session(challenge_id, session_id, session["user_id"])


@app.get("/data/{challenge_id}")
def data(challenge_id: str, request: Request):
    session_id, _ = require_session(request)
    instance = load_session_instance(challenge_id, session_id)
    return public_instance_response(instance, reused=True)


@app.post("/check/{challenge_id}")
@app.post("/api/challenges/{challenge_id}/check")
def check(challenge_id: str, request: Request):
    session_id, session = require_session(request)
    return check_for_session(challenge_id, session_id, session["user_id"])
