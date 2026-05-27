#!/usr/bin/env python3
"""End-to-end local portal flow for 04-convergence.

This script simulates one logged-in user:
1. bind wallet by signing a nonce
2. request faucet funding
3. run solver.py
4. ask the portal checker for the flag
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct


CHALLENGE_ID = os.getenv("CHALLENGE_ID", "04-convergence")
PORTAL_URL = os.getenv("PORTAL_URL", "http://localhost:8080").rstrip("/")
RPC_URL = os.getenv("RPC_URL", "http://localhost:8545")
USER_ID = os.getenv("USER_ID", "user-local")
ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "metadata" / "portal_state.json"


def request_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        f"{PORTAL_URL}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-User-Id": USER_ID,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def account_from_env():
    private_key = os.getenv("PRIVKEY", "").strip()
    if private_key:
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"
        return Account.from_key(private_key), private_key

    account = Account.create()
    private_key = "0x" + account.key.hex()
    print("[portal-test] generated fresh wallet")
    print(f"export WALLET_ADDR={account.address}")
    print(f"export PRIVKEY={private_key}")
    return account, private_key


def run_solver(private_key: str) -> None:
    env = os.environ.copy()
    env["RPC_URL"] = RPC_URL
    env["PRIVKEY"] = private_key
    subprocess.run([sys.executable, "solver.py"], cwd=ROOT, env=env, check=True)


def main() -> None:
    if os.getenv("RESET_PORTAL_STATE", "").lower() in {"1", "true", "yes"}:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
            print(f"[portal-test] reset local portal state: {STATE_PATH}")

    account, private_key = account_from_env()
    wallet = account.address

    print(f"[portal-test] portal: {PORTAL_URL}")
    print(f"[portal-test] user:   {USER_ID}")
    print(f"[portal-test] wallet: {wallet}")

    nonce = request_json(
        "POST",
        f"/api/challenges/{CHALLENGE_ID}/wallet/nonce",
        {"wallet_address": wallet},
    )
    message = encode_defunct(text=nonce["message"])
    signature = account.sign_message(message).signature.hex()

    bound = request_json(
        "POST",
        f"/api/challenges/{CHALLENGE_ID}/wallet/bind",
        {"wallet_address": wallet, "signature": signature},
    )
    print(f"[portal-test] bound:  {bound['bound']}")

    faucet = request_json("POST", f"/api/challenges/{CHALLENGE_ID}/faucet")
    print(f"[portal-test] faucet: {faucet}")

    before = request_json("POST", f"/api/challenges/{CHALLENGE_ID}/check")
    print(f"[portal-test] solved before solver: {before['solved']}")

    if not before["solved"]:
        run_solver(private_key)

    after = request_json("POST", f"/api/challenges/{CHALLENGE_ID}/check")
    print(json.dumps(after, indent=2))

    if not after.get("solved"):
        raise SystemExit("[portal-test] expected solved=true")


if __name__ == "__main__":
    main()
