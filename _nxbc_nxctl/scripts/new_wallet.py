#!/usr/bin/env python3
"""Generate a local EVM wallet for testing.

This is a client-side helper. It does not contact the RPC and does not fund the
wallet. Keep the printed private key local to the player.
"""

from eth_account import Account


account = Account.create()

print(f"Address:     {account.address}")
print(f"Private key: 0x{account.key.hex()}")
print()
print("Shell exports:")
print(f"export WALLET_ADDR={account.address}")
print(f"export PRIVKEY=0x{account.key.hex()}")
