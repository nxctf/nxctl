# 04 Convergence Local Portal

This is a local NXCTF-like backend for the blockchain POC. It proves the safer flag flow:

```text
user session -> bound wallet -> Factory.isSolved(wallet) -> return flag
```

The real flag is only in the backend service environment. It is not stored in the contract, ABI, public metadata, or frontend.

## Start

```sh
docker compose up --build
```

Services:

```text
http://localhost:8545  public filtered JSON-RPC
http://localhost:8080  local portal/checker API
```

## End-To-End Test

From `_nxbc_nxctl`:

```sh
python3 scripts/test_portal_flow.

rm metadata/portal_state.json
python3 scripts/test_portal_flow.py
```

The script generates a wallet if `PRIVKEY` is not set, binds it to `USER_ID=user-local`, asks the portal faucet for ETH, runs `solver.py`, then calls the checker endpoint. Expected final output includes:

```json
{
  "solved": true,
  "flag": "TCP1P{local_convergence_flag_from_backend}"
}
```

If you previously ran the old team-based prototype and see `wallet is already bound to another user`, reset the local POC state:

```sh
RESET_PORTAL_STATE=1 python3 scripts/test_portal_flow.py
```

## Manual Flow

In this POC, `X-User-Id` simulates the logged-in user session. In real NXCTF, the backend should get this from auth/session, not from a user-controlled header.

Get challenge metadata:

```sh
curl -s http://localhost:8080/api/challenges/04-convergence \
  -H "X-User-Id: user-a"
```

Generate or choose a wallet:

```sh
python3 scripts/new_wallet.py
export WALLET_ADDR=0x...
export PRIVKEY=0x...
```

Request a bind nonce:

```sh
curl -s http://localhost:8080/api/challenges/04-convergence/wallet/nonce \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-a" \
  -d "{\"wallet_address\":\"$WALLET_ADDR\"}"
```

Sign the returned `message` with the wallet private key, then bind:

```sh
curl -s http://localhost:8080/api/challenges/04-convergence/wallet/bind \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-a" \
  -d "{\"wallet_address\":\"$WALLET_ADDR\",\"signature\":\"0x...\"}"
```

For manual testing, the Python end-to-end script is easier because it signs this message for you.

Request faucet funding:

```sh
curl -s -X POST http://localhost:8080/api/challenges/04-convergence/faucet \
  -H "X-User-Id: user-a"
```

Run the solver with the same wallet:

```sh
export RPC_URL=http://localhost:8545
python3 solver.py
```

Check and receive the flag:

```sh
curl -s -X POST http://localhost:8080/api/challenges/04-convergence/check \
  -H "X-User-Id: user-a"
```

## What This Proves

- One shared RPC endpoint can support many users.
- Each user binds one wallet with a signature.
- The checker does not trust a wallet address submitted during check.
- The checker reads the wallet bound to the logged-in user.
- The contract remains the public source of solved state.
- The backend remains the private source of the flag.

## What Is Still POC-Only

- `X-User-Id` is fake auth.
- State is JSON in `metadata/portal_state.json`, not a database.
- Faucet key is a public Anvil dev key.
- CORS is open for local testing.
- No rate limiting beyond one faucet record per wallet.
- No production secret manager.
