# NXBCL Architecture Audit & Design Document

> **Scope**: Multi-challenge CTF launcher portal with per-challenge PoW, session gating, runtime lifecycle, and nxctl as runtime/tunnel adapter.
>
> **Date**: 2026-05-28
>
> **Status**: Draft — awaiting review

---

## 1. Audit Summary

### What exists today

`_nxbc_nxctl` is a single-challenge POC launcher for `04-convergence`. It runs as a monolithic FastAPI app (`portal/app.py`, 588 lines) that handles everything inline:

- PoW challenge issuance and verification
- Session cookie management
- Wallet generation, funding, and contract spawning (via `web3.py`)
- Instance lifecycle (launch, check, data)
- State persistence to a flat JSON file (`metadata/portal_state.json`)
- Static HTML frontend (`portal/static/index.html`, 668 lines)

**nxctl** is a separate, mature runtime orchestration system with its own SQLite DB, Docker Compose lifecycle, tunnel providers (ngrok, cloudflare, pinggy, bore), TTL/daemon, and a FastAPI API layer. It manages challenges, ports, exports, and runtime instances at the container level.

### Core architectural verdict

The POC works for a single hardcoded challenge. It is **not ready for multi-challenge** without significant restructuring. Key issues:

1. **Single-challenge hardcoding** — `CHALLENGE_ID`, factory ABI, and contract interactions are all module-level constants.
2. **Monolith problem** — Auth, PoW, blockchain interaction, state persistence, and lifecycle are all interleaved in one file.
3. **Flat JSON state** — `portal_state.json` is a single unbounded JSON blob (already 30KB of accumulated PoW challenges that never get cleaned). No transactions, no concurrent safety, no expiration sweep.
4. **No nxctl integration** — The POC runs Docker Compose directly via `docker-compose.yml` and interacts with Anvil/contracts manually. nxctl's runtime/export capabilities are unused.
5. **No real frontend** — The UI is a single HTML file with inline CSS/JS, hardcoded to one challenge, no routing, no challenge selection, no state machine.

---

## 2. Risks & Findings

### Critical

| # | Risk | Impact |
|---|------|--------|
| R1 | **JSON file as DB** — `portal_state.json` grows unbounded, has no transaction support, and corrupts under concurrent writes from multiple workers. | Data loss, race conditions, duplicate instances |
| R2 | **No PoW challenge expiration sweep** — Expired PoW tokens accumulate forever. State file already has 40+ unused tokens. | Memory/disk growth, stale data confusion |
| R3 | **Instance key is `session_id:challenge_id`** — If a user gets a new session (e.g., cookie cleared), their old instance becomes orphaned but the on-chain setup persists. | Leaked wallets, orphaned contract state |
| R4 | **No rate limiting** — `POST /challenge` can be spammed to fill the state file and exhaust server entropy. | DoS vector |
| R5 | **CORS allow-all** — `allow_origins=["*"]` in production would allow any origin to call the API with cookies. | Session hijacking |

### High

| # | Risk | Impact |
|---|------|--------|
| R6 | **Single-challenge architecture** — `CHALLENGE_ID`, `FACTORY_ABI`, `SETUP_ABI` are module-level constants. Adding chall-2 requires forking the entire app. | No scalability |
| R7 | **Web3 calls inside HTTP handlers** — `spawn_setup` and `fund_wallet` do synchronous blockchain transactions inside FastAPI route handlers. Under load these block the event loop. | Timeouts, poor UX |
| R8 | **No session-to-challenge scoping** — PoW session is global; once you solve it, you can launch any challenge. The requirement says PoW should be per-challenge. | Auth bypass for challenge isolation |
| R9 | **Private keys in JSON** — Disposable wallet private keys are stored in the state file indefinitely. | Key exposure risk |
| R10 | **No instance TTL enforcement** — `expires_at` is checked on access but never swept. Expired instances linger in state. | State bloat, confusion |

### Medium

| # | Risk | Impact |
|---|------|--------|
| R11 | `X-User-Id` header is trusted for PoW issuance — any client can set any user ID. | Impersonation (acceptable in local POC, not in prod) |
| R12 | No extend/restart endpoints exist yet. | Missing lifecycle operations |
| R13 | No health check for the blockchain backend beyond initial connection test. | Silent failures |

---

## 3. Recommended Architecture

### Layered boundary model

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (SPA)                          │
│   Challenge Select → PoW Gate → Launch → Monitor → Check   │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────┴──────────────────────────────────┐
│                   LAUNCHER API (FastAPI)                     │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Auth /   │ │ Challenge│ │ Launcher │ │  Runtime      │  │
│  │ Session  │ │ Registry │ │ Service  │ │  Adapter      │  │
│  │ Module   │ │          │ │ (PoW +   │ │  (nxctl)      │  │
│  │          │ │          │ │ Wallet + │ │               │  │
│  │          │ │          │ │ Lifecycle│ │               │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬───────┘  │
│       │            │            │               │           │
│  ┌────┴────────────┴────────────┴───────────────┴────────┐  │
│  │              LAUNCHER DATABASE (SQLite)                │  │
│  │  sessions | pow_challenges | instances | solves        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                    nxctl adapter calls
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                    NXCTL (library import)                    │
│                                                             │
│  RuntimeService → Docker Compose → Containers               │
│  ExportManager  → Tunnel providers → Public URLs            │
│  Own SQLite DB  → runtime_instances, challenge_ports, ...   │
└─────────────────────────────────────────────────────────────┘
```

### Boundary definitions

| Boundary | Owns | Does NOT own |
|----------|------|--------------|
| **Portal Auth** | Session cookies, session lifecycle, session validation | PoW logic, runtime state |
| **Challenge Registry** | Challenge metadata, per-challenge config (ABI, factory address, chain config), challenge list | Runtime instances, sessions |
| **PoW Gate** | PoW issuance, validation, anti-spam, single-use token enforcement | Sessions (delegates to auth module), runtime |
| **Launcher Service** | Instance lifecycle (launch/extend/restart/check), wallet provisioning, challenge-specific contract interaction, instance TTL | Container management (delegates to nxctl adapter), tunnel management |
| **Runtime Adapter (nxctl)** | Container start/stop/status, port allocation, tunnel export/unexport, Docker Compose lifecycle | Launcher sessions, PoW, wallet/key management, on-chain state |
| **Launcher DB** | sessions, pow_challenges, launcher_instances, solves, wallet records | nxctl's runtime_instances, challenge_ports, challenge_exports |
| **nxctl DB** | Runtime container state, port assignments, export records, TTL for containers | Launcher sessions, PoW state, wallet material |

---

## 4. Recommended Flow: Challenge-first → PoW → Session → Launch/Check

```
Browser                    Launcher API                    nxctl / Chain
  │                            │                              │
  ├─ GET /api/challenges ──────►                              │
  │◄─ challenge list ──────────┤                              │
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/start ─────────────►── nxctl.start(challenge) ───►│
  │◄─ { status: "running" } ───┤◄─ runtime started ──────────┤
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/pow/challenge ─────►                              │
  │◄─ { token, prefix, ... } ──┤                              │
  │                            │                              │
  │  [browser solves PoW]      │                              │
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/pow/solution ──────►── verify + set session ──────│
  │◄─ { session: "active" } ───┤                              │
  │  [Set-Cookie: nxbcl_sess]  │                              │
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/launch ────────────►── provision wallet ──────────│
  │   [Cookie: nxbcl_sess]     │── fund wallet ──────────────►│
  │                            │── spawn setup ──────────────►│
  │◄─ { rpc_url, privkey, ..}──┤                              │
  │                            │                              │
  │  [user runs solver]        │                              │
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/check ─────────────►── isSolved() ───────────────►│
  │   [Cookie: nxbcl_sess]     │◄─ true/false ────────────────┤
  │◄─ { solved, flag? } ───────┤                              │
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/extend ────────────►── extend TTL ────────────────│
  │   [Cookie: nxbcl_sess]     │                              │
  │                            │                              │
  ├─ POST /api/challenges      │                              │
  │   /{id}/restart ───────────►── restart runtime ──────────►│
  │   [Cookie: nxbcl_sess]     │── re-provision wallet ──────►│
  │◄─ { new instance data } ───┤                              │
```

### Key ordering constraint

1. **Start** (runtime) — can happen before auth, creates the container/chain
2. **PoW** — per-challenge, produces a single-use token
3. **Session** — set after PoW verification, scoped to user + challenge
4. **Launch** — requires valid session, provisions wallet + contract, returns solver data
5. **Check/Extend/Restart** — require valid session

This means the runtime (Docker/Anvil chain) is **already running** before a specific user authenticates. The launcher provisions per-user state (wallet, setup contract) on top of the shared running chain.

---

## 5. Folder Structure

```
nxbcl/
├── AGENTS.md                          # this project's engineering rules
├── pyproject.toml                     # Python package config
├── requirements.txt
│
├── challenges/                        # challenge-specific bundles
│   ├── 04-convergence/
│   │   ├── contracts/
│   │   │   ├── Challenge.sol
│   │   │   ├── ChallengeFactory.sol
│   │   │   └── Setup.sol
│   │   ├── artifacts/                 # compiled ABIs, metadata
│   │   │   ├── ChallengeFactory.abi.json
│   │   │   └── Setup.abi.json
│   │   ├── scripts/
│   │   │   ├── deploy.sh
│   │   │   └── rpc_proxy.py
│   │   ├── docker-compose.yml         # challenge runtime definition
│   │   ├── foundry.toml
│   │   ├── metadata.json              # factory addr, chain config
│   │   ├── solver.py                  # reference solver
│   │   └── challenge.yml              # challenge descriptor
│   │
│   └── 05-another-chall/              # future challenges same structure
│       ├── ...
│       └── challenge.yml
│
├── launcher/                          # backend Python package
│   ├── __init__.py
│   ├── app.py                         # FastAPI app factory
│   ├── config.py                      # launcher configuration
│   ├── dependencies.py                # FastAPI dependency injection
│   │
│   ├── auth/                          # session & auth boundary
│   │   ├── __init__.py
│   │   ├── session.py                 # session CRUD, validation
│   │   └── middleware.py              # session cookie middleware
│   │
│   ├── pow/                           # PoW gate boundary
│   │   ├── __init__.py
│   │   └── service.py                 # issue, verify, anti-spam
│   │
│   ├── challenges/                    # challenge registry boundary
│   │   ├── __init__.py
│   │   ├── registry.py                # discover & load challenge configs
│   │   └── models.py                  # ChallengeConfig, ChainConfig, etc.
│   │
│   ├── instances/                     # launcher instance lifecycle
│   │   ├── __init__.py
│   │   ├── service.py                 # launch, extend, restart, check
│   │   ├── wallet.py                  # wallet generation, funding
│   │   └── models.py                  # LauncherInstance, WalletInfo
│   │
│   ├── runtime/                       # nxctl adapter boundary
│   │   ├── __init__.py
│   │   └── adapter.py                 # thin wrapper around nxctl services
│   │
│   ├── db/                            # launcher-own database
│   │   ├── __init__.py
│   │   ├── schema.py                  # table definitions
│   │   ├── connection.py              # connection factory
│   │   └── migrations.py              # schema migrations
│   │
│   └── routes/                        # API routes (thin adapters)
│       ├── __init__.py
│       ├── challenges.py              # /api/challenges/*
│       ├── pow.py                     # /api/challenges/{id}/pow/*
│       ├── instances.py               # /api/challenges/{id}/launch|check|extend|restart
│       └── health.py                  # /api/health
│
├── frontend/                          # SPA frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── tsconfig.json
│   │
│   ├── public/
│   │   └── favicon.svg
│   │
│   └── src/
│       ├── main.ts                    # entry point
│       ├── App.vue                    # root component (or App.tsx)
│       ├── router.ts                  # client-side routing
│       │
│       ├── api/                       # API client
│       │   ├── client.ts
│       │   └── types.ts
│       │
│       ├── stores/                    # state management
│       │   ├── session.ts
│       │   ├── challenge.ts
│       │   └── instance.ts
│       │
│       ├── views/                     # page components
│       │   ├── ChallengeList.vue
│       │   ├── ChallengeLauncher.vue
│       │   └── NotFound.vue
│       │
│       ├── components/                # reusable UI components
│       │   ├── PowSolver.vue
│       │   ├── InstancePanel.vue
│       │   ├── CountdownTimer.vue
│       │   ├── CopyField.vue
│       │   └── StatusBadge.vue
│       │
│       └── styles/
│           ├── variables.css
│           ├── global.css
│           └── components.css
│
├── data/                              # runtime data (gitignored)
│   ├── launcher.db                    # launcher SQLite
│   └── logs/
│
├── tests/
│   ├── test_pow.py
│   ├── test_session.py
│   ├── test_launch.py
│   ├── test_check.py
│   └── test_e2e_flow.py
│
├── docker-compose.yml                 # dev orchestration (portal + chain)
├── docker-compose.prod.yml            # production overrides
├── Dockerfile                         # launcher backend image
└── Makefile                           # dev shortcuts
```

---

## 6. Module Responsibilities

### 6.1 `launcher/auth/`

```python
# session.py
class SessionService:
    def create_session(user_id: str, challenge_id: str) -> Session
    def validate_session(session_id: str, challenge_id: str) -> Session
    def expire_sessions() -> int  # sweep
    def revoke_session(session_id: str) -> None
```

- Session is scoped to `(user_id, challenge_id)`.
- Cookie name: `nxbcl_session`.
- TTL: configurable, default 24h.
- Storage: `launcher.db` → `sessions` table.

### 6.2 `launcher/pow/`

```python
# service.py
class PowService:
    def issue_challenge(user_id: str, challenge_id: str) -> PowChallenge
    def verify_solution(user_id: str, challenge_id: str, token: str, solution: str) -> None
    def sweep_expired() -> int
```

- Per-challenge PoW issuance.
- Single-use tokens.
- Rate limit: max N active challenges per user per challenge per window.
- Storage: `launcher.db` → `pow_challenges` table.

### 6.3 `launcher/challenges/`

```python
# registry.py
class ChallengeRegistry:
    def load_challenges(challenges_dir: Path) -> list[ChallengeConfig]
    def get_challenge(challenge_id: str) -> ChallengeConfig
    def list_challenges() -> list[ChallengeConfig]
```

- Reads `challenge.yml` from each challenge directory.
- Provides ABI, factory address, chain config, flag, runtime config.
- Stateless — config comes from filesystem, not DB.

```yaml
# challenges/04-convergence/challenge.yml
id: "04-convergence"
name: "Convergence"
description: "EVM challenge involving contract convergence"
kind: "blockchain_rpc"
chain:
  family: evm
  id: 31337
  rpc_internal: "http://anvil:8545"
  rpc_public: "http://localhost:8545"
factory:
  address: "0x5FbDB2315678afecb367f032d93F642f64180aa3"
  abi_path: "artifacts/ChallengeFactory.abi.json"
  spawn_function: "spawnFor(address)"
setup:
  abi_path: "artifacts/Setup.abi.json"
  checker: "isSolved()"
flag: "${FLAG_04_CONVERGENCE}"
faucet:
  amount_eth: "0.2"
  funder_key: "${FUNDER_PRIVKEY}"
pow:
  difficulty: "000"    # 3 leading zeros
  ttl_seconds: 120
instance:
  ttl_seconds: 1800
  extend_seconds: 600
```

### 6.4 `launcher/instances/`

```python
# service.py
class InstanceService:
    def launch(session: Session, challenge: ChallengeConfig) -> LauncherInstance
    def check(session: Session, challenge: ChallengeConfig) -> CheckResult
    def extend(session: Session, challenge: ChallengeConfig) -> LauncherInstance
    def restart(session: Session, challenge: ChallengeConfig) -> LauncherInstance
    def get_active(session_id: str, challenge_id: str) -> Optional[LauncherInstance]
    def sweep_expired() -> int

# wallet.py
class WalletService:
    def create_wallet() -> WalletInfo
    def fund_wallet(client: Web3, funder: Account, address: str, amount: str) -> str
    def spawn_setup(client: Web3, factory: Contract, funder: Account, player: str) -> str
```

- Instance keyed by `(user_id, challenge_id)`, NOT `(session_id, challenge_id)`.
  - This prevents orphan instances when a user's session rotates.
- Wallet creation is a separate concern from launch.
- Contract interaction uses explicit client/factory injection, not globals.

### 6.5 `launcher/runtime/adapter.py`

```python
class NxctlAdapter:
    """Thin wrapper around nxctl's RuntimeService for container lifecycle."""

    def __init__(self, nxctl_config, nxctl_db_path: str):
        self._runtime_svc = RuntimeService(nxctl_config, nxctl_db_path, ...)

    def start_challenge(self, challenge_id: str) -> RuntimeStatus
    def stop_challenge(self, challenge_id: str) -> bool
    def restart_challenge(self, challenge_id: str) -> RuntimeStatus
    def extend_challenge(self, challenge_id: str) -> RuntimeStatus
    def get_status(self, challenge_id: str) -> RuntimeStatus
    def export_tunnel(self, challenge_id: str, provider: str) -> TunnelInfo
    def unexport_tunnel(self, challenge_id: str) -> bool
```

- Imports nxctl as a Python library (not shell-out).
- Uses nxctl's OWN SQLite DB — completely separate from launcher DB.
- Passes explicit config and db_path — no shared singletons.
- Returns data contract objects (see Section 9), not nxctl internal models.

### 6.6 `launcher/routes/`

Routes are thin adapters. Example:

```python
# routes/instances.py
@router.post("/api/challenges/{challenge_id}/launch")
async def launch(challenge_id: str, request: Request):
    session = require_session(request, challenge_id)      # auth check
    challenge = registry.get_challenge(challenge_id)       # config lookup
    instance = instance_service.launch(session, challenge) # business logic
    return serialize_instance(instance)                    # response
```

No business logic in routes. No direct DB access. No web3 calls.

---

## 7. Launcher Database Schema

Separate SQLite at `data/launcher.db`. NOT shared with nxctl's DB.

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,              -- random token (session cookie value)
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,        -- scoped per challenge
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, challenge_id)     -- one active session per user per challenge
);

CREATE TABLE pow_challenges (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    prefix TEXT NOT NULL,
    zero_prefix TEXT NOT NULL DEFAULT '000',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    solved_at TEXT,
    solution TEXT,
    digest TEXT
);

CREATE TABLE launcher_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    session_id TEXT,                    -- which session created this
    rpc_url TEXT,
    chain_id INTEGER,
    wallet_address TEXT,
    private_key TEXT,                   -- encrypted in prod
    factory_address TEXT,
    setup_address TEXT,
    challenge_address TEXT,
    fund_tx TEXT,
    spawn_tx TEXT,
    status TEXT DEFAULT 'active',      -- active | expired | solved
    solved INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(user_id, challenge_id)      -- one active instance per user per challenge
);

CREATE TABLE solves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    wallet_address TEXT,
    setup_address TEXT,
    solved_at TEXT NOT NULL,
    flag_issued INTEGER DEFAULT 0,
    UNIQUE(user_id, challenge_id)
);

-- Indexes
CREATE INDEX idx_sessions_user_challenge ON sessions(user_id, challenge_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
CREATE INDEX idx_pow_expires ON pow_challenges(expires_at);
CREATE INDEX idx_instances_user_challenge ON launcher_instances(user_id, challenge_id);
CREATE INDEX idx_instances_expires ON launcher_instances(expires_at);
```

---

## 8. API Contract

### 8.1 Challenge listing

```
GET /api/challenges
→ 200
{
  "challenges": [
    {
      "id": "04-convergence",
      "name": "Convergence",
      "kind": "blockchain_rpc",
      "chain_id": 31337,
      "runtime_status": "running" | "stopped" | "unknown",
      "has_active_session": true | false,
      "has_active_instance": true | false
    }
  ]
}
```

### 8.2 Challenge detail

```
GET /api/challenges/{challenge_id}
→ 200
{
  "id": "04-convergence",
  "name": "Convergence",
  "kind": "blockchain_rpc",
  "chain_id": 31337,
  "rpc_url": "http://localhost:8545",
  "factory_address": "0x...",
  "runtime_status": "running",
  "instance": {                              // null if no active instance
    "wallet_address": "0x...",
    "setup_contract": "0x...",
    "expires_in": 1234,
    "solved": false
  }
}
```

### 8.3 Start runtime (before PoW)

```
POST /api/challenges/{challenge_id}/start
→ 200  { "status": "running", "message": "Runtime is ready" }
→ 200  { "status": "already_running", "message": "Runtime was already active" }
→ 503  { "error": "Failed to start runtime" }
```

No auth required — this starts the shared chain, not user-specific state.

### 8.4 PoW challenge issuance

```
POST /api/challenges/{challenge_id}/pow/challenge
Headers: X-User-Id: <user_id>
→ 200
{
  "challenge_token": "...",
  "prefix": "...",
  "zero_prefix": "000",
  "algorithm": "sha256(prefix + ':' + solution)",
  "expires_in": 120
}
→ 429  { "error": "Rate limited" }
```

### 8.5 PoW solution submission (sets session)

```
POST /api/challenges/{challenge_id}/pow/solution
Headers: X-User-Id: <user_id>
Body: { "challenge_token": "...", "solution": "..." }
→ 200
{
  "session": "active",
  "challenge_id": "04-convergence",
  "expires_at": "2026-05-28T..."
}
Set-Cookie: nxbcl_session=<token>; HttpOnly; SameSite=Lax; Path=/
→ 400  { "error": "invalid/expired/used challenge" }
```

### 8.6 Launch (requires session)

```
POST /api/challenges/{challenge_id}/launch
Cookie: nxbcl_session=<token>
→ 200
{
  "challenge_id": "04-convergence",
  "rpc_url": "http://localhost:8545",
  "chain_id": 31337,
  "wallet_address": "0x...",
  "private_key": "0x...",
  "setup_contract": "0x...",
  "challenge_contract": "0x...",
  "factory_address": "0x...",
  "expires_in": 1800,
  "reused": false
}
→ 401  { "error": "missing/expired session" }
```

### 8.7 Check (requires session)

```
POST /api/challenges/{challenge_id}/check
Cookie: nxbcl_session=<token>
→ 200
{
  "challenge_id": "04-convergence",
  "solved": true,
  "flag": "TCP1P{...}"          // only when solved
}
→ 401  { "error": "missing/expired session" }
→ 400  { "error": "no active instance" }
```

### 8.8 Extend (requires session)

```
POST /api/challenges/{challenge_id}/extend
Cookie: nxbcl_session=<token>
→ 200
{
  "challenge_id": "04-convergence",
  "expires_in": 2400,
  "extended_by": 600
}
→ 400  { "error": "too early to extend" | "no active instance" }
→ 429  { "error": "extend cooldown active, wait Ns" }
```

### 8.9 Restart (requires session)

```
POST /api/challenges/{challenge_id}/restart
Cookie: nxbcl_session=<token>
→ 200
{
  "challenge_id": "04-convergence",
  "rpc_url": "...",
  "wallet_address": "0x...",      // NEW wallet
  "private_key": "0x...",         // NEW key
  "setup_contract": "0x...",      // NEW setup
  "expires_in": 1800,
  "restarted": true
}
→ 429  { "error": "restart cooldown active, wait Ns" }
```

**Restart semantics**: Generates a new wallet, new setup contract, resets TTL. Old instance is marked `replaced`. Does NOT restart the Docker container (the chain continues running).

### 8.10 Instance data (requires session)

```
GET /api/challenges/{challenge_id}/data
Cookie: nxbcl_session=<token>
→ 200  { ...same shape as launch response, "reused": true }
→ 400  { "error": "no active instance" }
```

Used for refresh/restore without re-launching.

---

## 9. nxctl Integration Strategy

### Principle: nxctl as runtime adapter, not state owner

```
Launcher ──import──► nxctl.RuntimeService   (start/stop/extend containers)
Launcher ──import──► nxctl.ExportManager    (tunnel management)
Launcher ──DOES NOT──► nxctl.db             (no direct DB access)
```

### Data contract between launcher and nxctl

Launcher → nxctl (input):

```python
@dataclass
class RuntimeRequest:
    challenge_id: str      # maps to nxctl challenge name
    challenge_path: str    # relative path to challenge dir
    # nxctl figures out ports, compose, containers
```

nxctl → launcher (output):

```python
@dataclass
class RuntimeStatus:
    challenge_id: str
    status: str           # "running" | "stopped" | "error"
    host_ports: list[int] # allocated ports
    started_at: str | None
    expires_at: str | None

@dataclass
class TunnelInfo:
    challenge_id: str
    provider: str
    public_url: str
    protocol: str
    target_port: int
    status: str
```

### Integration rules

1. **Separate DBs**: nxctl uses `data/nxctl.db`, launcher uses `data/launcher.db`. No cross-reads.
2. **Explicit instantiation**: The adapter creates `RuntimeService(config, db_path, cache_dir)` with explicit paths. No global singletons.
3. **No import side effects**: Importing nxctl modules must not auto-create databases or start background threads.
4. **Challenge registration**: Challenges that the launcher manages should be pre-registered in nxctl's DB (via `ChallengeService.add_challenge()`) during launcher startup/sync.
5. **Error boundary**: nxctl exceptions are caught at the adapter layer and translated to launcher-domain errors.
6. **State reconciliation**: The launcher trusts nxctl for container status but owns all launcher-layer state (sessions, wallets, instances, solves).

### What NOT to share

| Data | Owner | NOT shared with |
|------|-------|-----------------|
| Sessions, PoW state | Launcher DB | nxctl |
| Wallet private keys | Launcher DB | nxctl |
| Solve records, flags | Launcher DB | nxctl |
| Container status | nxctl DB | Launcher DB (queried via adapter) |
| Port allocations | nxctl DB | Launcher DB |
| Export/tunnel records | nxctl DB | Launcher DB |

---

## 10. Frontend Recommendation

### Stack: **Vue 3 + Vite + Vanilla CSS**

| Choice | Reason |
|--------|--------|
| **Vue 3 (Composition API)** | Lightweight (~30KB), fast, great for state-driven UIs with reactive challenge/instance state. Simpler than React for this scope. Not overkill like Next.js. |
| **Vite** | Fast dev server, HMR, trivial build pipeline. No webpack config hell. |
| **Vue Router** | Client-side routing for `/challenges`, `/challenges/:id`, etc. |
| **Pinia** | Minimal store for session state, challenge list, active instance. |
| **Vanilla CSS** | Full control over design tokens, dark mode, animations. No Tailwind dependency. |
| **TypeScript** | Type safety for API contracts, prevents runtime surprises. |

### Why NOT React/Next.js

- This is a single-purpose launcher portal, not a general web app.
- No SSR needed — the SPA is served from the same FastAPI backend.
- Vue's reactivity model is more natural for the challenge state machine.
- Smaller bundle, fewer dependencies, faster iteration.

### Why NOT plain HTML

- Multi-challenge routing requires a router.
- Challenge state machine (idle → solving_pow → authenticated → launched → checking) needs reactive state management.
- The current inline JS already fights against complexity with manual DOM manipulation.
- A component model prevents the 668-line monolith from growing further.

### Frontend state machine per challenge

```
            ┌──────────┐
            │   IDLE   │ ← no session, no instance
            └────┬─────┘
                 │ click "Start"
            ┌────▼─────┐
            │ STARTING │ ← runtime starting
            └────┬─────┘
                 │ runtime ready
            ┌────▼──────┐
            │  POW_GATE │ ← solving PoW
            └────┬──────┘
                 │ PoW solved, session set
         ┌───────▼────────┐
         │ AUTHENTICATED  │ ← session active, no instance yet
         └───────┬────────┘
                 │ click "Launch"
          ┌──────▼───────┐
          │  LAUNCHING   │ ← provisioning wallet + setup
          └──────┬───────┘
                 │ instance ready
          ┌──────▼───────┐
          │   ACTIVE     │ ← instance running, solver data visible
          │              │── Extend (renew TTL)
          │              │── Check (verify solve)
          │              │── Restart (new wallet+setup)
          └──────┬───────┘
                 │ solved
          ┌──────▼───────┐
          │   SOLVED     │ ← flag displayed
          └──────────────┘
```

### Design guidelines

- **Dark theme default** with glassmorphism panels.
- **Challenge cards** on the landing page, each showing status badge.
- **Terminal-style** code output for solver env.
- **Countdown timer** component for instance TTL.
- **Copy buttons** on all fields.
- **Toast notifications** for async operations.
- **Loading spinners** during PoW solve and blockchain interactions.
- **Responsive** — works on mobile for quick checks.

---

## 11. State Isolation

### Per-user isolation

- Instance keyed by `(user_id, challenge_id)`, guaranteeing one active instance per user per challenge.
- Session keyed by `(user_id, challenge_id)`, guaranteeing one active session per user per challenge.
- Wallet is per-instance (one wallet per launch).

### Per-challenge isolation

- Each challenge has its own `challenge.yml` with its own factory address, ABI, chain config.
- PoW tokens include `challenge_id` — cannot reuse a PoW from chall-1 on chall-2.
- Sessions include `challenge_id` — a session for chall-1 cannot launch chall-2.
- Instances are fully scoped — chall-1 data never appears in chall-2 queries.

### Cross-service isolation

- Launcher DB: sessions, PoW, instances, solves.
- nxctl DB: containers, ports, exports.
- No cross-DB foreign keys. No shared tables.
- The only shared data is the minimal contract described in Section 9.

---

## 12. Anti-abuse Measures

| Threat | Mitigation |
|--------|------------|
| PoW spam | Rate limit: max 3 active PoW challenges per user per challenge. Expired tokens swept every 60s. |
| Session farming | One session per user per challenge. New PoW overwrites old session. |
| Duplicate instances | `UNIQUE(user_id, challenge_id)` in DB. Launch reuses active instance. |
| Instance hoarding | TTL enforcement. Sweep expired instances every 60s. |
| Race conditions | SQLite `BEGIN IMMEDIATE` for launch/extend/restart operations. |
| Restart abuse | Restart cooldown (configurable, default 300s). |
| Extend abuse | Extend only when remaining TTL < threshold. Extend cooldown (default 30s). |
| Flag fishing | Flag only returned when `isSolved()` is true on-chain. No client-side flag. |
| Session replay | `HttpOnly`, `SameSite=Lax` cookies. CORS restricted to portal origin in prod. |
| Header spoofing (`X-User-Id`) | In production, replace with real auth (OAuth/JWT). For now, acceptable in POC. |

---

## 13. Refactor Plan (Prioritized)

### Phase 1: Foundation (Critical — must do first)

| Step | What | Why | Risk |
|------|------|-----|------|
| 1.1 | Create `nxbcl/` project skeleton with folder structure from Section 5 | Everything else depends on this | Low |
| 1.2 | Create launcher SQLite schema (`launcher/db/schema.py`) | Replace the JSON state file | Low |
| 1.3 | Implement `SessionService` and `PowService` with SQLite backend | Core auth boundary | Low |
| 1.4 | Implement `ChallengeRegistry` that reads `challenge.yml` files | Multi-challenge support | Low |

### Phase 2: Core Lifecycle (High — core functionality)

| Step | What | Why | Risk |
|------|------|-----|------|
| 2.1 | Implement `InstanceService` with launch, check, extend, restart | Core launcher logic | Medium — blockchain interactions |
| 2.2 | Implement `WalletService` as a separate concern | Clean wallet lifecycle | Low |
| 2.3 | Extract `NxctlAdapter` from nxctl imports | Runtime boundary | Medium — need to verify nxctl import safety |
| 2.4 | Wire up FastAPI routes as thin adapters | API layer | Low |

### Phase 3: Frontend (High — user-visible)

| Step | What | Why | Risk |
|------|------|-----|------|
| 3.1 | Initialize Vue 3 + Vite project in `frontend/` | Frontend skeleton | Low |
| 3.2 | Implement challenge list view | Entry point | Low |
| 3.3 | Implement challenge launcher view with PoW + state machine | Core UX | Medium — state management |
| 3.4 | Style with dark theme, glassmorphism, animations | Visual polish | Low |

### Phase 4: Migration & Integration (Medium — connecting the pieces)

| Step | What | Why | Risk |
|------|------|-----|------|
| 4.1 | Migrate `04-convergence` into `challenges/04-convergence/` with `challenge.yml` | First real challenge bundle | Low |
| 4.2 | Wire nxctl adapter to actually start/stop containers | Runtime integration | Medium |
| 4.3 | Add PoW sweep and instance expiry sweep (background task or startup) | State hygiene | Low |
| 4.4 | Add rate limiting middleware | Anti-abuse | Low |

### Phase 5: Hardening (Lower priority but important)

| Step | What | Why | Risk |
|------|------|-----|------|
| 5.1 | Add CORS restrictions for production | Security | Low |
| 5.2 | Add SQLite `BEGIN IMMEDIATE` for mutating operations | Concurrency safety | Low |
| 5.3 | Encrypt private keys at rest in launcher DB | Key protection | Low |
| 5.4 | Add E2E test suite | Validation | Medium |
| 5.5 | Docker Compose for local dev (launcher + anvil + frontend) | Dev experience | Low |

### What to keep as-is

- **nxctl core** — Don't modify nxctl internals. Use it as a library.
- **Solidity contracts** — No changes needed. The factory/setup pattern works.
- **Docker Compose challenge definitions** — Keep per-challenge compose files.
- **PoW algorithm** — SHA-256 prefix search is fine for rate limiting.

---

## 14. Trade-offs

### SQLite vs PostgreSQL for launcher DB

**Choice: SQLite**

- ✅ Zero deployment overhead. Single file, embedded.
- ✅ Matches nxctl's existing pattern.
- ✅ Sufficient for CTF-scale concurrent users (dozens, not thousands).
- ⚠️ Write concurrency limited to one writer at a time (mitigated with WAL mode and `BEGIN IMMEDIATE`).
- ❌ Would need to switch to Postgres if serving hundreds of concurrent users.

**Verdict**: SQLite is correct for this project's scale. Switching later is straightforward since the DB layer is abstracted.

### Vue vs React vs Svelte

**Choice: Vue 3**

- ✅ Smaller bundle than React (~30KB vs ~130KB).
- ✅ Composition API matches the challenge state machine well.
- ✅ Single-file components keep related code together.
- ⚠️ Smaller ecosystem than React (but we need very few libraries).
- ❌ If the team is React-heavy, Vue adds learning cost.

**Acceptable alternative**: If the team prefers React, use Vite + React with Zustand for state. The architecture doesn't change.

### nxctl as library vs subprocess

**Choice: Library import**

- ✅ No subprocess overhead, no shell parsing, direct function calls.
- ✅ Explicit dependency injection (config, db_path).
- ✅ Matches nxctl's AGENTS.md guidance.
- ⚠️ Import-time side effects in nxctl must be verified (importing should not create DBs or start threads).
- ⚠️ Python version coupling between launcher and nxctl.
- ❌ If nxctl changes its internal API, the adapter must be updated.

**Mitigation**: The adapter layer absorbs API changes. Pin nxctl to a specific version/commit.

### PoW per-challenge vs global

**Choice: Per-challenge**

- ✅ Matches the specified flow (enter challenge → start runtime → solve PoW → get session → launch).
- ✅ Better isolation — compromising one challenge's PoW doesn't give access to others.
- ⚠️ More friction for users exploring multiple challenges (must solve PoW for each).
- ❌ Slightly more complex session management.

**Verdict**: Per-challenge PoW is the correct design per requirements. The friction is acceptable because each challenge is a separate CTF problem.

### Instance key: `user_id` vs `session_id`

**Choice: `user_id + challenge_id`**

- ✅ Instance survives session rotation (cookie clear → re-auth → same instance).
- ✅ Prevents orphaned instances when sessions expire.
- ✅ Natural deduplication (one instance per user per challenge).
- ⚠️ A user cannot have multiple simultaneous instances of the same challenge.
- ❌ Requires real user identification (not just session tokens).

**Verdict**: Using `user_id` is more robust than `session_id`. In the POC, `X-User-Id` header suffices. In production, replace with OAuth/JWT-derived user ID.

### Shared chain vs per-user chain

**Choice: Shared chain (current architecture)**

- ✅ One Anvil instance serves all users. Low resource usage.
- ✅ Factory pattern provides per-user isolation at the contract level.
- ⚠️ A user could theoretically interfere with another user's contracts (but `spawnFor` is owner-only).
- ❌ Chain state grows unbounded with many users (acceptable for CTF duration).

**Verdict**: Shared chain with per-user setup contracts is the correct design for CTF scale. Per-user chains would be wasteful.

---

## 15. Open Questions for Review

1. **Should `start` (runtime) be user-triggered or automatic?**
   - Current proposal: User clicks "Start" on a challenge, which starts the Docker runtime. Then PoW, then launch.
   - Alternative: Runtime is always pre-started by admin. Users only do PoW → launch.
   - Impact: If pre-started, the `/start` endpoint becomes admin-only.

2. **Should restart create a new wallet AND new setup, or just new setup?**
   - Current proposal: New wallet + new setup + new funding (full reset).
   - Alternative: Same wallet, just re-spawn setup.
   - Impact: If same wallet, the on-chain factory's `already spawned` check blocks re-spawn. Would need a factory `reset()` function.

3. **Production auth: What replaces `X-User-Id`?**
   - Options: OAuth2 (Google/GitHub), JWT from external auth service, or simple username/password.
   - Impact: Affects session service design and middleware.

4. **Should the frontend be served by FastAPI (same origin) or separately?**
   - Same origin: Simpler deployment, no CORS issues, SPA served as static files.
   - Separate: Decoupled deployment, CDN-friendly.
   - Recommendation: Same origin for simplicity. Vite builds to `static/`, FastAPI serves it.

5. **How many concurrent challenges are expected?**
   - 3-5 challenges: Current design is fine.
   - 10+: May need to consider resource limits per challenge (memory, ports).
   - 50+: Would need a fundamentally different architecture (k8s, per-challenge namespaces).
