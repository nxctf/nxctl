# NXBCL Architecture Audit Part 2: Data Directory, Sync Mechanism, and Configuration Strategy

> **Scope**: Specific audit of data layout rules, repository synchronization (`nxbcl sync`), and configuration integration between `nxctl` and the new blockchain CTF launcher portal (`nxbcl`).
>
> **Date**: 2026-05-28
>
> **Status**: Ready for Review

---

## 1. Unified Directory Layout

To align with `AGENTS.md` and `nxctl` engineering standards, all runtime artifacts, caches, state files, and logs for both core `nxctl` and the blockchain launcher `nxbcl` must reside inside designated data subdirectories. Writing runtime-generated files into source directories is strictly prohibited.

The proposed unified layout partitions data under a shared parent `data/` or a sister `data_nxbcl/` directory. For maximum isolation and simplicity, we recommend keeping a distinct `data_nxbcl/` directory structure side-by-side with the existing `data/` directory.

### Target Layout for Blockchain Launcher: `data_nxbcl/`
```text
data_nxbcl/
  nxbcl.db               # SQLite database for blockchain challenge sessions, PoW, and solvers
  chall/                 # Cloned blockchain challenge git repositories (cache only)
    04-convergence/      # E.g., cloned files, contracts, foundry config, deploy scripts
  runtime/
    locks/               # Instance and allocation mutexes
    state/               # Active instances, anvil process state, faucet tx logs
    tmp/                 # Generated files, ephemeral configs, credentials
  logs/
    anvil/               # Anvil RPC container or node process stdout/stderr logs
    faucet/              # Faucet execution and transaction logs
```

---

## 2. Config Strategy: `config.yml` vs Separate Config

A major design decision is where to store the blockchain launcher configs (e.g. faucet private keys, PoW difficulty, target RPC node, git challenge repository).

### Recommended Choice: Extend `config.yml` (Unified Config)
We recommend adding a dedicated `nxbcl` section to the root `config.yml` of the project.

**Why:**
- **Single Source of Truth**: Simplifies deployment and administration. An administrator configuring `nxctl` can configure the blockchain launcher in the exact same file.
- **Port Management Coordination**: Allows global port ranges (e.g. `ports` section in `config.yml`) to be shared or partitioned cleanly between container challenges and blockchain RPC endpoints.
- **Unified Environment Loading**: The existing `nxctl.core.config.py` uses Pydantic to parse and validate settings, including environment variable substitutions (like `${GITHUB_TOKEN}`). We can leverage or extend this parser directly.

### Proposed YAML Schema Additions to `config.yml`
```yaml
# Existing nxctl config sections: challenges, app, api, ttl, daemon, ports, tunnels...

# New Blockchain Launcher specific configuration
nxbcl:
  enabled: true
  data_dir: ./data_nxbcl

  # Git settings specifically for blockchain challenge repos
  git:
    github_repo: https://github.com/nxctf/blockchain-challenges.git
    branch: main
    access_token: ${GITHUB_TOKEN}

  # Proof of Work settings per challenge
  pow:
    zero_prefix: "0000"
    ttl_seconds: 120

  # Faucet settings
  faucet:
    amount_eth: "0.2"
    # The administrative private key that funds user accounts
    provider_private_key: ${FAUCET_PRIVATE_KEY}

  # Session parameters
  session:
    ttl_seconds: 86400
    instance_ttl_seconds: 1800
```

---

## 3. Sync Mechanism: `nxbcl sync`

Just as `nxctl` has a sync mechanism to clone/pull challenge sources, the blockchain launcher requires a deterministic command/subcommand to pull down the smart contract challenges, deploy scripts, and ABI definitions.

### How `nxbcl sync` Will Work:
1. **Source Discovery**: Reads `nxbcl.git.github_repo` from `config.yml`.
2. **Deterministic Cache Destination**: Uses the `data_nxbcl/chall/` directory.
3. **Library Reuse**: Imports and reuses `GitRepository` from `nxctl.core.git` to perform the clone or pull operation, ensuring identical support for authentication tokens and sparse/depth-1 cloning.
4. **Idempotency**: If the repo already exists, performs a pull. If checkout is corrupt, deletes and re-clones.

---

## 4. Verification and DB Integration

The POC launcher wrote state to `portal_state.json`. In production:
- All portal states (PoW tokens, session IDs, active user instances, wallet private keys) must be moved into a central SQLite database (`data_nxbcl/nxbcl.db`).
- We will define explicit tables:
  - `pow_challenges`: token, salt, difficulty, created_at, solved_at, user_ip.
  - `sessions`: session_id, user_id, created_at, expires_at.
  - `instances`: instance_id, session_id, challenge_id, wallet_address, private_key, deploy_address, rpc_port, created_at, expires_at.
