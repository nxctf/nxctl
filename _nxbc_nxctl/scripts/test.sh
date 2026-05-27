#!/bin/sh
set -eu

RPC_URL="${RPC_URL:-http://rpc:8545}"
PLAYER1_ADDRESS="${PLAYER1_ADDRESS:-0x70997970C51812dc3A010C7d01b50e0d17dc79C8}"
PLAYER1_PRIVATE_KEY="${PLAYER1_PRIVATE_KEY:-0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d}"
PLAYER2_ADDRESS="${PLAYER2_ADDRESS:-0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC}"
DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
ONE_HUNDRED_ETHER="100000000000000000000"
ZERO32="0x0000000000000000000000000000000000000000000000000000000000000000"

FACTORY_ADDRESS="$(python3 - <<'PY'
import json
from pathlib import Path

print(json.loads(Path("metadata/metadata.json").read_text())["factory_address"])
PY
)"

echo "[04-convergence] factory: ${FACTORY_ADDRESS}"
echo "[04-convergence] player1: ${PLAYER1_ADDRESS}"
echo "[04-convergence] player2: ${PLAYER2_ADDRESS}"

docker compose exec -T anvil cast send \
  --rpc-url "$RPC_URL" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  "$FACTORY_ADDRESS" \
  "spawnFor(address)" \
  "$PLAYER1_ADDRESS"

SETUP1_ADDRESS="$(docker compose exec -T anvil cast call \
  --rpc-url "$RPC_URL" \
  "$FACTORY_ADDRESS" \
  "setupOf(address)(address)" \
  "$PLAYER1_ADDRESS" | tr -d '\r')"

CHALLENGE1_ADDRESS="$(docker compose exec -T anvil cast call \
  --rpc-url "$RPC_URL" \
  "$SETUP1_ADDRESS" \
  "challenge()(address)" | tr -d '\r')"

echo "[04-convergence] setup: ${SETUP1_ADDRESS}"
echo "[04-convergence] challenge: ${CHALLENGE1_ADDRESS}"

docker compose exec -T anvil cast send \
  --rpc-url "$RPC_URL" \
  --private-key "$PLAYER1_PRIVATE_KEY" \
  "$CHALLENGE1_ADDRESS" \
  "registerSeeker()"

FRAGMENTS="["
i=0
while [ "$i" -lt 10 ]; do
  if [ "$i" -gt 0 ]; then
    FRAGMENTS="${FRAGMENTS},"
  fi
  FRAGMENTS="${FRAGMENTS}(${PLAYER1_ADDRESS},${ONE_HUNDRED_ETHER},0x)"
  i=$((i + 1))
done
FRAGMENTS="${FRAGMENTS}]"

TRUTH="$(docker compose exec -T anvil cast abi-encode \
  "f((address,uint256,bytes)[],bytes32,uint32,address,address)" \
  "$FRAGMENTS" \
  "$ZERO32" \
  0 \
  "$PLAYER1_ADDRESS" \
  "$PLAYER1_ADDRESS" | tr -d '\r')"

echo "[04-convergence] binding pact and transcending"
docker compose exec -T anvil cast send \
  --rpc-url "$RPC_URL" \
  --private-key "$PLAYER1_PRIVATE_KEY" \
  "$SETUP1_ADDRESS" \
  "bindPact(bytes)" \
  "$TRUTH"

docker compose exec -T anvil cast send \
  --rpc-url "$RPC_URL" \
  --private-key "$PLAYER1_PRIVATE_KEY" \
  "$CHALLENGE1_ADDRESS" \
  "transcend(bytes)" \
  "$TRUTH"

PLAYER1_SOLVED="$(docker compose exec -T anvil cast call --rpc-url "$RPC_URL" "$FACTORY_ADDRESS" "isSolved(address)(bool)" "$PLAYER1_ADDRESS" | tr -d '\r')"
PLAYER2_SOLVED="$(docker compose exec -T anvil cast call --rpc-url "$RPC_URL" "$FACTORY_ADDRESS" "isSolved(address)(bool)" "$PLAYER2_ADDRESS" | tr -d '\r')"

echo "[04-convergence] player1 solved: ${PLAYER1_SOLVED}"
echo "[04-convergence] player2 solved: ${PLAYER2_SOLVED}"

if [ "$PLAYER1_SOLVED" != "true" ] || [ "$PLAYER2_SOLVED" != "false" ]; then
  echo "[04-convergence] FAIL" >&2
  exit 1
fi

echo "[04-convergence] PASS"
