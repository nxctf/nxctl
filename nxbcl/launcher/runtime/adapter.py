import logging
import secrets
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class NxctlAdapter:
    """Stub runtime adapter for NXBCL.
    
    This class simulates interacting with nxctl container/compose lifecycles.
    In Phase 2, this will be replaced with real imports of nxctl's orchestration layer:
    
        from nxctl.scripts.runtime_service import RuntimeService
        from nxctl.scripts.exports.manager import ExportManager
        
    Integration Strategy for Phase 2:
    1. Keep one shared blockchain compose runtime alive for the challenge repo.
    2. Expose only the safe HTTP RPC proxy.
    3. Lazily deploy the requested challenge factory if metadata is missing.
    4. Generate and fund a disposable player wallet.
    5. Call factory.spawnFor(wallet) and store the returned setup address.
    6. Return RPC_URL, PRIVKEY, and SETUP_ADDR to the launcher response.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def start_instance(self, session_id: str, challenge_id: str) -> Dict[str, Any]:
        """Simulate dynamic provisioning of a blockchain challenge instance.
        
        The real adapter should return a per-user setup address, not a new
        chain. deploy_address is kept as a legacy alias for setup_address while
        the POC database schema still uses that column name.
        """
        # Generate a dummy disposable wallet and private key for the user
        private_key = "0x" + secrets.token_hex(32)
        # Mock address derivation (simplification for Phase 1)
        wallet_address = "0x" + secrets.token_hex(20)
        setup_address = "0x" + secrets.token_hex(20)
        
        # Simulate the shared RPC proxy exposed by the challenge repo compose stack.
        rpc_port = 8545
        
        return {
            "instance_id": secrets.token_hex(16),
            "challenge_id": challenge_id,
            "wallet_address": wallet_address,
            "private_key": private_key,
            "setup_address": setup_address,
            "deploy_address": setup_address,
            "rpc_url": f"http://localhost:{rpc_port}",
            "rpc_port": rpc_port,
            "chain_id": 31337,
            "status": "running"
        }
