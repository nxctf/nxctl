#!/usr/bin/env python3
"""Local server-side faucet simulator for the Convergence POC.

This represents what NXCTF should do later: fund a submitted player wallet
without exposing the faucet private key to the player or to solver.py.
"""

import json
import os
import sys
from pathlib import Path

from web3 import Web3


STATE_PATH = Path("metadata/faucet_state.json")
DEFAULT_AMOUNT_ETH = "0.2"
MIN_BALANCE_ETH = "0.05"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"missing env: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def normalize_private_key(value: str) -> str:
    return value if value.startswith("0x") else f"0x{value}"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def send_tx(w3: Web3, account, tx):
    tx.setdefault("from", account.address)
    tx.setdefault("nonce", w3.eth.get_transaction_count(account.address))
    tx.setdefault("gas", 21_000)
    tx.setdefault("chainId", w3.eth.chain_id)

    dynamic_fee = (
        "maxFeePerGas" in tx
        or "maxPriorityFeePerGas" in tx
        or tx.get("type") in (2, "0x2")
    )
    if dynamic_fee:
        tx.pop("gasPrice", None)
    else:
        tx.setdefault("gasPrice", w3.eth.gas_price)

    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"faucet transaction failed: {tx_hash.hex()}")
    return receipt


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python3 scripts/faucet.py 0xPlayerAddress", file=sys.stderr)
        sys.exit(1)

    rpc_url = require_env("RPC_URL")
    funder_private_key = normalize_private_key(require_env("FUNDER_PRIVKEY"))
    recipient = Web3.to_checksum_address(sys.argv[1])

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise RuntimeError(f"could not connect to RPC: {rpc_url}")

    funder = w3.eth.account.from_key(funder_private_key)
    amount = w3.to_wei(os.getenv("FAUCET_AMOUNT_ETH", DEFAULT_AMOUNT_ETH), "ether")
    min_balance = w3.to_wei(os.getenv("FAUCET_MIN_BALANCE_ETH", MIN_BALANCE_ETH), "ether")
    balance = w3.eth.get_balance(recipient)

    state = load_state()
    funded = state.setdefault("funded", {})
    key = recipient.lower()

    print(f"rpc:       {rpc_url}")
    print(f"recipient: {recipient}")
    print(f"balance:   {w3.from_wei(balance, 'ether')} ETH")

    if balance >= min_balance:
        print("[faucet] skip: wallet already has enough ETH")
        return

    if key in funded:
        print(f"[faucet] skip: wallet was already funded in tx {funded[key]['tx_hash']}")
        return

    receipt = send_tx(w3, funder, {"to": recipient, "value": amount})

    funded[key] = {
        "address": recipient,
        "amount_eth": str(w3.from_wei(amount, "ether")),
        "tx_hash": receipt.transactionHash.hex(),
    }
    save_state(state)

    print(f"[faucet] funded: {w3.from_wei(amount, 'ether')} ETH")
    print(f"[faucet] tx:     {receipt.transactionHash.hex()}")


if __name__ == "__main__":
    main()
