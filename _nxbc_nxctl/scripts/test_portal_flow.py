#!/usr/bin/env python3
"""End-to-end NXBC launcher flow for 04-convergence.

This script simulates one logged-in NXCTF user:
1. call Launch
2. receive disposable wallet/private key/setup info
3. run solver.py with the launcher wallet
4. call Check/Get Flag
"""

import json
import hashlib
import http.cookiejar
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


CHALLENGE_ID = os.getenv("CHALLENGE_ID", "04-convergence")
PORTAL_URL = os.getenv("PORTAL_URL", "http://localhost:8080").rstrip("/")
RPC_URL = os.getenv("RPC_URL", "http://localhost:8545")
USER_ID = os.getenv("USER_ID", "user-local")
ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "metadata" / "portal_state.json"
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))


def request_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        f"{PORTAL_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    if path in {"/challenge", "/api/challenge", "/solution", "/api/solution"}:
        req.add_header("X-User-Id", USER_ID)
    try:
        with OPENER.open(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def solve_pow(challenge: dict) -> str:
    prefix = challenge["prefix"]
    zero_prefix = challenge["zero_prefix"]
    nonce = 0
    while True:
        solution = str(nonce)
        digest = hashlib.sha256(f"{prefix}:{solution}".encode()).hexdigest()
        if digest.startswith(zero_prefix):
            return solution
        nonce += 1


def run_solver(instance: dict) -> None:
    env = os.environ.copy()
    env["RPC_URL"] = RPC_URL
    env["PRIVKEY"] = instance["private_key"]
    env["SETUP_ADDR"] = instance["setup_contract"]
    subprocess.run([sys.executable, "solver.py"], cwd=ROOT, env=env, check=True)


def main() -> None:
    if os.getenv("RESET_PORTAL_STATE", "").lower() in {"1", "true", "yes"}:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
            print(f"[launcher-test] reset local portal state: {STATE_PATH}")

    print(f"[launcher-test] portal: {PORTAL_URL}")
    print(f"[launcher-test] user:   {USER_ID}")

    challenge = request_json("POST", "/challenge")
    solution = solve_pow(challenge)
    session = request_json(
        "POST",
        "/solution",
        {
            "challenge_token": challenge["challenge_token"],
            "solution": solution,
        },
    )
    print(f"[launcher-test] session: {session['session']}")

    instance = request_json("POST", f"/launch/{CHALLENGE_ID}")
    print("[launcher-test] launch:")
    print(json.dumps(instance, indent=2))

    before = request_json("POST", f"/check/{CHALLENGE_ID}")
    print(f"[launcher-test] solved before solver: {before['solved']}")

    if not before["solved"]:
        run_solver(instance)

    after = request_json("POST", f"/check/{CHALLENGE_ID}")
    print("[launcher-test] check:")
    print(json.dumps(after, indent=2))

    if not after.get("solved"):
        raise SystemExit("[launcher-test] expected solved=true")


if __name__ == "__main__":
    main()
