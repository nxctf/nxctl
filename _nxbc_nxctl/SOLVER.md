# 04 Convergence Solver

This solver is the factory-aware version of the original `_tmp/convergence/solver.py`.

The old solver expected a ready `SETUP_ADDR`. In this shared-chain model, players get a `FACTORY_ADDR`, then the solver calls `spawn()` and reads the player's setup address.

## Secure Flow

Player side:

```text
generate wallet -> keep PRIVKEY -> submit WALLET_ADDR -> run solver
```

Server/NXCTF side:

```text
receive WALLET_ADDR -> faucet funds wallet -> checker uses FACTORY.isSolved(WALLET_ADDR)
```

The player solver must not receive the faucet/deployer private key.

## Local Portal / Flag Flow

This challenge now has a local NXCTF-like portal in Docker Compose:

```text
http://localhost:8080
```

It simulates:

```text
user session -> bind wallet -> faucet -> check solved -> return flag
```

Fastest full test:

```sh
python3 scripts/test_portal_flow.py
```

That script generates or uses `PRIVKEY`, binds the wallet to `USER_ID=user-local`, funds it through the portal, runs `solver.py`, then calls the checker. The flag is returned by the portal only after `ChallengeFactory.isSolved(bound_wallet)` is true.

More details are in `PORTAL.md`.

## Get Factory Address

After `docker compose up --build` succeeds:

```sh
cat metadata/metadata.json
```

Or export it directly:

```sh
export FACTORY_ADDR=$(python3 -c "import json; print(json.load(open('metadata/metadata.json'))['factory_address'])")
```

## Get A Local Private Key

For this local Anvil POC, use one of Anvil's funded test keys.

Player 1:

```sh
export PRIVKEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
```

Player 2:

```sh
export PRIVKEY=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
```

or if u want create your own key:

```sh
pip install eth-account
python3 << 'EOF'
from eth_account import Account

acct = Account.create()

print("Address:", acct.address)
print("Private key:", "0x" + acct.key.hex())
EOF
```

```bash
export PRIVKEY=0x333203a6a75baa3ad67076ac8837ad13a18b76b4672d362985ab2b3f3cef1fcf
```

or with
```bash
cast wallet new
```

These are public Anvil development keys. Do not use them anywhere real.

## Local Faucet Test

If you generated a fresh wallet, it has zero ETH. Fund it with the local faucet simulator:

```sh
export RPC_URL=http://localhost:8545
export FUNDER_PRIVKEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
python3 scripts/faucet.py "$WALLET_ADDR"
```

`FUNDER_PRIVKEY` is server-side only. Do not put it in `solver.py`, and do not give it to players.

## Run

Install Python deps if needed:

```sh
python3 -m pip install web3 eth-abi
```

Then:

```sh
export RPC_URL=http://localhost:8545
# export FACTORY_ADDR=$(python3 -c "import json; print(json.load(open('metadata/metadata.json'))['factory_address'])")
# export PRIVKEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
python3 solver.py
```

Expected ending:

```text
solved:   True
```



```bash
rm metadata/portal_state.json
python3 scripts/test_portal_flow.py
```
