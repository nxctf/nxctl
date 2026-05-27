#!/bin/sh
set -eu

RPC_URL="${RPC_URL:-http://anvil:8545}"
PUBLIC_RPC_URL="${PUBLIC_RPC_URL:-http://localhost:8545}"
RPC_PORT="${RPC_PORT:-8545}"
CHAIN_ID="${CHAIN_ID:-31337}"
DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-}"
CHALLENGE_NAME="${CHALLENGE_NAME:-blockchain-challenge}"
FACTORY_CONTRACT="${FACTORY_CONTRACT:-contracts/ChallengeFactory.sol:ChallengeFactory}"
SETUP_CONTRACT="${SETUP_CONTRACT:-}"
CHECKER="${CHECKER:-ChallengeFactory.isSolved(address)}"
SPAWN_FUNCTION="${SPAWN_FUNCTION:-spawnFor(address)}"

if [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
  echo "DEPLOYER_PRIVATE_KEY is required" >&2
  exit 1
fi

mkdir -p artifacts metadata

echo "[deploy] waiting for Anvil at ${RPC_URL}"
i=0
until cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "[deploy] Anvil did not become ready" >&2
    exit 1
  fi
  sleep 1
done

echo "[deploy] building ${CHALLENGE_NAME}"
forge build
forge inspect "$FACTORY_CONTRACT" abi > artifacts/ChallengeFactory.abi.json
if [ -n "$SETUP_CONTRACT" ]; then
  forge inspect "$SETUP_CONTRACT" abi > artifacts/Setup.abi.json
fi

echo "[deploy] deploying ${FACTORY_CONTRACT}"
DEPLOY_OUTPUT="$(forge create \
  --rpc-url "$RPC_URL" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  --broadcast \
  "$FACTORY_CONTRACT")"

echo "$DEPLOY_OUTPUT"
FACTORY_ADDRESS="$(printf "%s\n" "$DEPLOY_OUTPUT" | sed -n 's/^Deployed to: //p' | tail -n 1)"

if [ -z "$FACTORY_ADDRESS" ]; then
  echo "[deploy] failed to parse factory address" >&2
  exit 1
fi

SETUP_ABI_JSON="null"
if [ -n "$SETUP_CONTRACT" ]; then
  SETUP_ABI_JSON="\"artifacts/Setup.abi.json\""
fi

cat > metadata/metadata.json <<EOF
{
  "challenge_name": "${CHALLENGE_NAME}",
  "kind": "blockchain_rpc",
  "protocol": "http",
  "chain_family": "evm",
  "chain_id": ${CHAIN_ID},
  "rpc_url": "${PUBLIC_RPC_URL}",
  "rpc_port": ${RPC_PORT},
  "factory_address": "${FACTORY_ADDRESS}",
  "factory_abi": "artifacts/ChallengeFactory.abi.json",
  "setup_abi": ${SETUP_ABI_JSON},
  "deployment_mode": "static_factory",
  "isolation_scope": "shared_chain_per_player_contract",
  "spawn_function": "${SPAWN_FUNCTION}",
  "checker": "${CHECKER}"
}
EOF

echo "[deploy] wrote metadata/metadata.json"
cat metadata/metadata.json
