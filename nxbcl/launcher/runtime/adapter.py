import logging
import os
import secrets
import json
import subprocess
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class NxctlAdapter:
    """Real runtime adapter for NXBCL.

    Interacts with the local shared blockchain Compose stack, deploys
    factories, funds disposable user wallets, and spawns setup instances.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def start_instance(self, session_id: str, challenge_id: str) -> Dict[str, Any]:
        """Dynamically provision a blockchain challenge instance on the shared chain."""
        has_web3 = False
        try:
            from web3 import Web3
            from eth_account import Account
            has_web3 = True
        except ImportError:
            pass

        chall_dir = self.data_dir / "chall"

        # 1. Start Docker Compose for anvil and rpc if not already running
        if chall_dir.exists():
            try:
                subprocess.run(
                    ["docker", "compose", "up", "-d", "anvil", "rpc"],
                    cwd=str(chall_dir),
                    shell=(os.name == "nt"),
                    capture_output=True,
                    check=True
                )
            except Exception as e:
                logger.warning(f"Failed to run docker compose up: {e}")

        # 1b. If web3 is available, verify that the RPC node is actually reachable
        #     before doing any provisioning. Fail fast if it's not.
        if has_web3:
            from web3 import Web3 as _W3

            w3_check = _W3(_W3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 5}))
            if not w3_check.is_connected():
                w3_check = _W3(_W3.HTTPProvider("http://localhost:8545", request_kwargs={"timeout": 5}))
            if not w3_check.is_connected():
                raise RuntimeError(
                    "RPC node is not reachable. Start the RPC server first before launching a challenge."
                )

        # 2. Check if factory needs to be deployed (metadata missing OR contract code not present on active chain)
        metadata_file = chall_dir / "metadata" / "challenges" / challenge_id / "metadata.json"

        existing_factory = None
        if metadata_file.exists():
            try:
                with open(metadata_file, "r") as f:
                    meta = json.load(f)
                    existing_factory = meta.get("factory_address")
            except Exception:
                pass

        need_deploy = True
        if existing_factory and has_web3:
            local_rpc = "http://127.0.0.1:8545"
            w3 = Web3(Web3.HTTPProvider(local_rpc))
            if not w3.is_connected():
                w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))
            if w3.is_connected():
                try:
                    code = w3.eth.get_code(w3.to_checksum_address(existing_factory))
                    if code and code != b"" and code != b"\x00":
                        need_deploy = False
                except Exception:
                    pass
        elif metadata_file.exists():
            # If metadata exists but has_web3 is False, assume it is deployed
            need_deploy = False

        if chall_dir.exists() and need_deploy:
            logger.info(f"Deploying factory for challenge {challenge_id}...")
            try:
                result = subprocess.run(
                    ["docker", "compose", "run", "--rm",
                     "-e", "DEPLOYER_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
                     "forge", "scripts/deploy_one.sh", challenge_id],
                    cwd=str(chall_dir),
                    shell=(os.name == "nt"),
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Deploy stdout: {result.stdout[-500:] if result.stdout else '(empty)'}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Factory deploy failed (exit {e.returncode}): {e.stderr[-500:] if e.stderr else e.stdout[-500:] if e.stdout else '(no output)'}")
            except Exception as e:
                logger.error(f"Failed to deploy factory via deploy_one.sh: {e}")

        # 3. Read metadata.json to get active parameters
        factory_address = None
        rpc_url = "http://localhost:8545"
        chain_id = 31337

        if metadata_file.exists():
            try:
                with open(metadata_file, "r") as f:
                    meta = json.load(f)
                    factory_address = meta.get("factory_address")
                    rpc_url = meta.get("rpc_url") or rpc_url
                    chain_id = meta.get("chain_id") or chain_id
            except Exception as e:
                logger.warning(f"Failed to read metadata: {e}")

        if not factory_address:
            factory_address = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

        # 4. Interact with Blockchain via Web3 if available
        if has_web3:
            local_rpc = "http://127.0.0.1:8545"
            w3 = Web3(Web3.HTTPProvider(local_rpc))
            if not w3.is_connected():
                w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))

            # At this point w3 MUST be connected (we verified above)
            player = Account.create()
            private_key = player.key.hex()
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            wallet_address = player.address

            try:
                # Faucet fund
                funder_private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
                funder = w3.eth.account.from_key(funder_private_key)

                # Send 0.2 ETH
                tx = {
                    "to": wallet_address,
                    "value": w3.to_wei("0.2", "ether"),
                    "gas": 21000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": w3.eth.get_transaction_count(funder.address),
                    "chainId": w3.eth.chain_id,
                }
                signed = funder.sign_transaction(tx)
                w3.eth.send_raw_transaction(signed.raw_transaction)

                # Spawn setup contract
                factory_abi = [
                    {
                        "inputs": [{"internalType": "address", "name": "player", "type": "address"}],
                        "name": "spawnFor",
                        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                        "stateMutability": "nonpayable",
                        "type": "function",
                    },
                    {
                        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
                        "name": "setupOf",
                        "outputs": [{"internalType": "contract Setup", "name": "", "type": "address"}],
                        "stateMutability": "view",
                        "type": "function",
                    }
                ]

                factory = w3.eth.contract(address=w3.to_checksum_address(factory_address), abi=factory_abi)

                # Call spawnFor(player)
                spawn_tx = factory.functions.spawnFor(wallet_address).build_transaction({
                    "from": funder.address,
                    "gas": 3000000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": w3.eth.get_transaction_count(funder.address),
                    "chainId": w3.eth.chain_id,
                })
                signed_spawn = funder.sign_transaction(spawn_tx)
                tx_hash = w3.eth.send_raw_transaction(signed_spawn.raw_transaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)

                # Get setup address
                setup_address = factory.functions.setupOf(wallet_address).call()
            except Exception as e:
                raise RuntimeError(
                    f"Failed to provision wallet/contracts on chain: {e}"
                )
        else:
            # Dev fallback: no web3 installed, generate stub data
            logger.warning("web3 not installed — returning stub instance data (dev mode only)")
            private_key = "0x" + secrets.token_hex(32)
            wallet_address = "0x" + secrets.token_hex(20)
            setup_address = "0x" + secrets.token_hex(20)

        return {
            "instance_id": secrets.token_hex(16),
            "challenge_id": challenge_id,
            "wallet_address": wallet_address,
            "private_key": private_key,
            "setup_address": setup_address,
            "deploy_address": setup_address,
            "rpc_url": rpc_url,
            "rpc_port": 8545,
            "chain_id": chain_id,
            "status": "running"
        }
