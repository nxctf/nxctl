import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3


CHALLENGE_ID = os.getenv("CHALLENGE_ID", "04-convergence")
RPC_URL = os.getenv("RPC_URL", "http://anvil:8545")
PUBLIC_RPC_URL = os.getenv("PUBLIC_RPC_URL", "http://localhost:8545")
PORTAL_PUBLIC_URL = os.getenv("PORTAL_PUBLIC_URL", "http://localhost:8080")
METADATA_PATH = Path(os.getenv("METADATA_PATH", "metadata/metadata.json"))
STATE_PATH = Path(os.getenv("STATE_PATH", "metadata/portal_state.json"))
FLAG = os.getenv("FLAG", "TCP1P{local_flag_not_configured}")
FAUCET_AMOUNT_ETH = os.getenv("FAUCET_AMOUNT_ETH", "0.2")
FAUCET_MIN_BALANCE_ETH = os.getenv("FAUCET_MIN_BALANCE_ETH", "0.05")


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
        "name": "isSolved",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class WalletRequest(BaseModel):
    wallet_address: str


class BindRequest(BaseModel):
    wallet_address: str
    signature: str


app = FastAPI(title="04-convergence local NXCTF portal")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_challenge(challenge_id: str) -> None:
    if challenge_id != CHALLENGE_ID:
        raise HTTPException(status_code=404, detail="unknown challenge")


def require_user(x_user_id: str | None) -> str:
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id header")
    return user_id


def checksum_address(address: str) -> str:
    try:
        return Web3.to_checksum_address(address)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid wallet address") from exc


def normalize_private_key(value: str) -> str:
    return value if value.startswith("0x") else f"0x{value}"


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
    state.setdefault("nonces", {})
    state.setdefault("wallets", {})
    state.setdefault("faucet", {})
    state.setdefault("solves", {})
    return state


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_PATH, state)


def load_metadata() -> dict[str, Any]:
    metadata = load_json(METADATA_PATH, {})
    if not metadata.get("factory_address"):
        raise HTTPException(status_code=503, detail="challenge metadata is not ready")
    return metadata


def w3() -> Web3:
    client = Web3(Web3.HTTPProvider(RPC_URL))
    if not client.is_connected():
        raise HTTPException(status_code=503, detail="rpc is not reachable")
    return client


def factory_contract(client: Web3):
    metadata = load_metadata()
    factory_address = Web3.to_checksum_address(metadata["factory_address"])
    return client.eth.contract(address=factory_address, abi=FACTORY_ABI)


def nonce_key(user_id: str, wallet: str) -> str:
    return f"{user_id}:{wallet.lower()}"


def solve_key(user_id: str, challenge_id: str) -> str:
    return f"{user_id}:{challenge_id}"


def build_bind_message(user_id: str, wallet: str, nonce: str) -> str:
    return "\n".join(
        [
            "NXCTF local wallet binding",
            f"challenge: {CHALLENGE_ID}",
            f"user: {user_id}",
            f"wallet: {wallet}",
            f"nonce: {nonce}",
        ]
    )


def get_bound_wallet(state: dict[str, Any], user_id: str) -> str:
    record = state["wallets"].get(user_id)
    if not record:
        raise HTTPException(status_code=400, detail="user has no bound wallet")
    return checksum_address(record["wallet_address"])


def assert_wallet_not_bound_to_other_user(
    state: dict[str, Any], user_id: str, wallet: str
) -> None:
    wallet_lower = wallet.lower()
    for existing_user, record in state["wallets"].items():
        if existing_user != user_id and record["wallet_address"].lower() == wallet_lower:
            raise HTTPException(
                status_code=409,
                detail="wallet is already bound to another user",
            )


def send_faucet_tx(client: Web3, recipient: str):
    funder_key = os.getenv("FUNDER_PRIVKEY", "").strip()
    if not funder_key:
        raise HTTPException(status_code=503, detail="faucet is not configured")

    funder = client.eth.account.from_key(normalize_private_key(funder_key))
    amount = client.to_wei(FAUCET_AMOUNT_ETH, "ether")
    tx = {
        "from": funder.address,
        "to": recipient,
        "value": amount,
        "nonce": client.eth.get_transaction_count(funder.address),
        "gas": 21_000,
        "gasPrice": client.eth.gas_price,
        "chainId": client.eth.chain_id,
    }
    signed = funder.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = client.eth.send_raw_transaction(raw)
    receipt = client.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise HTTPException(status_code=500, detail="faucet transaction failed")
    return receipt


@app.get("/")
def index():
    return {
        "service": "04-convergence local NXCTF portal",
        "challenge_id": CHALLENGE_ID,
        "portal_url": PORTAL_PUBLIC_URL,
        "routes": [
            f"/api/challenges/{CHALLENGE_ID}",
            f"/api/challenges/{CHALLENGE_ID}/wallet/nonce",
            f"/api/challenges/{CHALLENGE_ID}/wallet/bind",
            f"/api/challenges/{CHALLENGE_ID}/faucet",
            f"/api/challenges/{CHALLENGE_ID}/check",
        ],
    }


@app.get("/health")
def health():
    client = w3()
    metadata_ready = METADATA_PATH.exists()
    return {
        "ok": True,
        "chain_id": client.eth.chain_id,
        "metadata_ready": metadata_ready,
    }


@app.get("/api/challenges/{challenge_id}")
def challenge(challenge_id: str, x_user_id: str | None = Header(default=None)):
    require_challenge(challenge_id)
    metadata = load_metadata()
    state = load_state()
    user_wallet = None
    if x_user_id:
        record = state["wallets"].get(x_user_id)
        if record:
            user_wallet = record["wallet_address"]

    return {
        "challenge_id": challenge_id,
        "kind": "blockchain_rpc",
        "protocol": "http",
        "chain_family": "evm",
        "chain_id": metadata.get("chain_id", 31337),
        "rpc_url": metadata.get("rpc_url", PUBLIC_RPC_URL),
        "factory_address": metadata["factory_address"],
        "checker": "ChallengeFactory.isSolved(address)",
        "wallet_address": user_wallet,
        "flag_delivery": "server_side_check",
    }


@app.post("/api/challenges/{challenge_id}/wallet/nonce")
def wallet_nonce(
    challenge_id: str,
    body: WalletRequest,
    x_user_id: str | None = Header(default=None),
):
    require_challenge(challenge_id)
    user_id = require_user(x_user_id)
    wallet = checksum_address(body.wallet_address)
    state = load_state()
    assert_wallet_not_bound_to_other_user(state, user_id, wallet)

    nonce = secrets.token_hex(16)
    message = build_bind_message(user_id, wallet, nonce)
    state["nonces"][nonce_key(user_id, wallet)] = {
        "nonce": nonce,
        "message": message,
        "created_at": now_iso(),
    }
    save_state(state)

    return {
        "user_id": user_id,
        "wallet_address": wallet,
        "nonce": nonce,
        "message": message,
    }


@app.post("/api/challenges/{challenge_id}/wallet/bind")
def wallet_bind(
    challenge_id: str,
    body: BindRequest,
    x_user_id: str | None = Header(default=None),
):
    require_challenge(challenge_id)
    user_id = require_user(x_user_id)
    wallet = checksum_address(body.wallet_address)
    state = load_state()
    assert_wallet_not_bound_to_other_user(state, user_id, wallet)

    pending = state["nonces"].get(nonce_key(user_id, wallet))
    if not pending:
        raise HTTPException(status_code=400, detail="nonce not found")

    message = encode_defunct(text=pending["message"])
    recovered = Account.recover_message(message, signature=body.signature)
    if Web3.to_checksum_address(recovered) != wallet:
        raise HTTPException(status_code=400, detail="signature does not match wallet")

    state["wallets"][user_id] = {
        "wallet_address": wallet,
        "bound_at": now_iso(),
    }
    state["nonces"].pop(nonce_key(user_id, wallet), None)
    save_state(state)

    return {
        "user_id": user_id,
        "wallet_address": wallet,
        "bound": True,
    }


@app.get("/api/challenges/{challenge_id}/wallet")
def wallet_status(challenge_id: str, x_user_id: str | None = Header(default=None)):
    require_challenge(challenge_id)
    user_id = require_user(x_user_id)
    state = load_state()
    record = state["wallets"].get(user_id)
    return {
        "user_id": user_id,
        "wallet_address": record["wallet_address"] if record else None,
        "bound": bool(record),
    }


@app.post("/api/challenges/{challenge_id}/faucet")
def faucet(challenge_id: str, x_user_id: str | None = Header(default=None)):
    require_challenge(challenge_id)
    user_id = require_user(x_user_id)
    state = load_state()
    wallet = get_bound_wallet(state, user_id)
    client = w3()

    balance = client.eth.get_balance(wallet)
    min_balance = client.to_wei(FAUCET_MIN_BALANCE_ETH, "ether")
    faucet_record = state["faucet"].get(wallet.lower())

    if balance >= min_balance:
        return {
            "wallet_address": wallet,
            "funded": False,
            "reason": "wallet already has enough ETH",
            "balance_eth": str(client.from_wei(balance, "ether")),
        }

    if faucet_record:
        return {
            "wallet_address": wallet,
            "funded": False,
            "reason": "wallet was already funded",
            "tx_hash": faucet_record["tx_hash"],
            "balance_eth": str(client.from_wei(balance, "ether")),
        }

    receipt = send_faucet_tx(client, wallet)
    amount = client.to_wei(FAUCET_AMOUNT_ETH, "ether")
    state["faucet"][wallet.lower()] = {
        "user_id": user_id,
        "wallet_address": wallet,
        "amount_eth": str(client.from_wei(amount, "ether")),
        "tx_hash": receipt.transactionHash.hex(),
        "funded_at": now_iso(),
    }
    save_state(state)

    return {
        "wallet_address": wallet,
        "funded": True,
        "amount_eth": str(client.from_wei(amount, "ether")),
        "tx_hash": receipt.transactionHash.hex(),
    }


@app.post("/api/challenges/{challenge_id}/check")
def check(challenge_id: str, x_user_id: str | None = Header(default=None)):
    require_challenge(challenge_id)
    user_id = require_user(x_user_id)
    state = load_state()
    wallet = get_bound_wallet(state, user_id)
    client = w3()
    factory = factory_contract(client)
    solved = bool(factory.functions.isSolved(wallet).call())

    if not solved:
        return {
            "user_id": user_id,
            "challenge_id": challenge_id,
            "wallet_address": wallet,
            "solved": False,
        }

    state["solves"][solve_key(user_id, challenge_id)] = {
        "wallet_address": wallet,
        "solved_at": now_iso(),
    }
    save_state(state)

    return {
        "user_id": user_id,
        "challenge_id": challenge_id,
        "wallet_address": wallet,
        "solved": True,
        "flag": FLAG,
    }
