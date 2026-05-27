# NXBC Launcher POC

This is a TCP1P-style launcher for `04-convergence`.

```text
user session -> launch -> temporary wallet + setup -> solve -> check -> flag
```

The real flag stays in the backend service environment. It is not stored in the contract, ABI, metadata, or frontend.

## Start

Because the contracts changed for launcher mode, recreate the compose stack:

```sh
docker compose down
docker compose up --build
```

Services:

```text
http://localhost:8545  filtered shared JSON-RPC
http://localhost:8080  launcher web UI
```

Open `http://localhost:8080`, enter a local user id, click Launch, then copy the solver env from the page.

The web UI solves a small launcher challenge first, then receives a session cookie. `X-User-Id` is only a local label in this POC; launch/check do not trust user id alone.

## End-To-End Test

From `_nxbc_nxctl`:

```sh
RESET_PORTAL_STATE=1 python3 scripts/test_portal_flow.py
```

The script calls Launch, receives a disposable wallet/private key/setup address, runs `solver.py`, then calls Check. Expected final output includes:

```json
{
  "solved": true,
  "flag": "TCP1P{local_convergence_flag_from_backend}"
}
```

## Manual Flow

In this POC, `/challenge` and `/solution` simulate TCP1P-style launcher auth and set a random `nxbc_session` cookie. In real NXCTF, backend code should get `user_id` from the auth/session, not from a user-controlled header.

Get a launcher challenge:

```sh
curl -s -c cookies.txt -b cookies.txt -X POST http://localhost:8080/challenge \
  -H "X-User-Id: user-a"
```

Find a `solution` where:

```text
sha256(prefix + ":" + solution) starts with zero_prefix
```

Submit the solution:

```sh
curl -s -c cookies.txt -b cookies.txt -X POST http://localhost:8080/solution \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-a" \
  -d '{"challenge_token":"...","solution":"..."}'
```

Launch:

```sh
curl -s -X POST http://localhost:8080/launch/04-convergence \
  -b cookies.txt
```

Response:

```json
{
  "rpc_url": "http://localhost:8545",
  "chain_id": 31337,
  "wallet_address": "0x...",
  "private_key": "0x...",
  "setup_contract": "0x...",
  "challenge_contract": "0x...",
  "expires_in": 1800
}
```

Run solver with the returned values:

```sh
export RPC_URL=http://localhost:8545
export PRIVKEY=0x...
export SETUP_ADDR=0x...
python3 solver.py
```

Check and receive the flag:

```sh
curl -s -X POST http://localhost:8080/check/04-convergence \
  -b cookies.txt
```

## What This Proves

- One shared RPC endpoint can support many users.
- The launcher generates disposable per-user wallets.
- The launcher funds wallets with test ETH.
- The launcher creates one setup contract per user with `Factory.spawnFor(wallet)`.
- The checker reads the setup owned by the logged-in user.
- The backend returns the flag only after `Setup.isSolved()` is true.

## What Is Still POC-Only

- `/challenge` and `/solution` are local fake auth.
- `X-User-Id` is accepted only when requesting/submitting the local launcher challenge.
- State is JSON in `metadata/portal_state.json`, not Postgres.
- The temporary private key is stored in local JSON for POC repeatability.
- The funder key is a public Anvil dev key.
- CORS is open for local testing.
- TTL is recorded but expired on access only.
- There is no production secret manager or rate limiter yet.
