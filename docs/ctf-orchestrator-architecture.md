# CTF Orchestration Architecture

## Goal
Build a container-based CTF challenge orchestration platform that uses Git repositories as the single source of truth, prebuilds images once, and reuses shared runtime instances for fast startup and efficient resource usage.

## Product Direction
- CLI first.
- API and web dashboard come later.
- Shared runtime per challenge, not per user.
- Fast startup through local cache and prebuilt images.
- Support HTTP and TCP exposure with pluggable tunnel providers.
- Support GitHub, GitLab, and Gitea.

## Core Principles
- Git repo is the canonical source for challenge code.
- Runtime should be idempotent and reusable.
- Build once, run many.
- Runtime state must be tracked centrally.
- Every action should be observable and recoverable.
- Infrastructure providers must be swappable.

## MVP Architecture
### 1. CLI Control Plane
The CLI is the main interface for admins.

Recommended command groups:
- `challenge sync`
- `challenge list`
- `challenge inspect`
- `challenge build`
- `challenge prebuild`
- `challenge start`
- `challenge stop`
- `challenge restart`
- `challenge revert`
- `challenge cleanup`
- `challenge logs`
- `challenge status`
- `challenge url`
- `challenge health`
- `tunnel list`
- `tunnel create`
- `tunnel destroy`
- `registry add`
- `registry update`
- `registry remove`

### 2. Registry and Source Sync
Challenge definitions are stored in a registry table and synced from Git.

Sync flow:
- Admin registers repository URL, branch, and challenge path.
- System clones or updates local cache.
- System detects Dockerfile or docker-compose.yml.
- System validates challenge metadata and structure.
- System creates or updates image build metadata.
- System marks challenge as ready.

### 3. Build and Cache Layer
The cache layer stores:
- repository mirrors
- extracted challenge source
- build metadata
- image tags and digests
- last sync timestamp
- health and validation status

Build policy:
- build only on sync or explicit rebuild
- reuse existing image when source revision is unchanged
- version images by repository digest + branch + path + build spec hash
- keep a small retention policy for old builds

### 4. Runtime Manager
Runtime manager owns shared challenge instances.

Responsibilities:
- start challenge if not running
- reuse existing instance if already active
- track activity and health
- enforce idle timeout
- enforce maximum runtime TTL
- support restart and revert with cooldown
- support cleanup of containers, networks, volumes, and tunnels

### 5. Tunnel and Exposure Layer with Multi-Token Support
A tunnel provider abstracts public exposure.

**Supported Providers:**
- **FRP**: Self-hosted reverse proxy (supports multiple servers)
- **ngrok**: Simple public tunneling (supports multiple accounts)
- **Rathole**: Lightweight P2P reverse proxy (supports multiple servers)

**Multi-Token Strategy:**
Each provider can have multiple tokens/servers for:
- **Token Rotation**: When one account hits rate limits or quota
- **Load Balancing**: Distribute tunnels across multiple servers/accounts
- **Failover**: Automatic fallback to next token/server on error
- **Rotation Strategies**:
  - `round-robin`: Distribute tunnels evenly across available tokens
  - `fallback`: Use first token, fallback to next on error

**Example Config:**
```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin
    tokens:
      - name: "ngrok-account-1"
        token: ${NGROK_TOKEN_1}
        region: us
      - name: "ngrok-account-2"
        token: ${NGROK_TOKEN_2}
        region: eu
      - name: "ngrok-account-3"
        token: ${NGROK_TOKEN_3}
        region: ap

  frp:
    enabled: true
    rotation_strategy: round-robin
    servers:
      - name: "frp-primary"
        server_addr: frp1.example.com
        server_port: 7000
        token: ${FRP_TOKEN_1}
      - name: "frp-secondary"
        server_addr: frp2.example.com
        server_port: 7000
        token: ${FRP_TOKEN_2}
```

**Exposure Rules:**
- HTTP challenge gets host-based or path-based public URL
- TCP challenge gets generated TCP endpoint
- Multiple exports supported per runtime (one challenge → multiple public URLs)
- Tunnel lifecycle follows runtime lifecycle
- Tunnel is destroyed automatically on cleanup

### 6. State and Event System
Maintain state centrally for runtime correctness.

Use cases:
- activity tracking
- idle detection
- health checking
- runtime monitoring
- event replay for debugging
- job coordination between workers

Recommended state model:
- `challenge_registry`
- `challenge_revision`
- `challenge_image`
- `runtime_instance`
- `runtime_event`
- `runtime_activity`
- `tunnel_binding`
- `job_queue`
- `worker_heartbeat`

## Simplified Lifecycle Flow (MVP)

### Sync
```
1. Clone/pull repository
2. Scan paths in config
3. For each path:
   - Check if Dockerfile or docker-compose.yml exists
   - Extract service_port from docker config
   - Insert/update challenge in DB
4. Done - no prebuild yet
```

### Start
```
1. Lookup challenge by name
2. Check if runtime_instance exists
3. If running:
   - Return public_url from existing exports
4. If stopped or missing:
   - Build image (if not cached)
   - docker compose up
   - Insert runtime_instance
   - Create tunnel via default_tunnel provider
   - Insert challenge_export
   - Return public_url
```

### Revert
```
1. Check cooldown (last_revert + 5min)
   - If in cooldown, reject with message
2. docker compose down -v
3. docker compose up -d
4. Update last_revert timestamp
5. Re-create tunnel if needed
6. Return public_url
```

### Idle Cleanup (Worker)
```
1. For each runtime_instance:
   - If last_activity + 15min < now:
     - docker compose down
     - Update status to 'stopped'
     - Delete all challenge_exports for this runtime
   - Keep container image for fast restart
```

### Export/Tunnel Allocation Flow

One runtime can have multiple exports (multiple public endpoints):

```
Challenge: web/sqli-basic
├── Runtime: container-abc123
├── Exports:
│   ├── Export 1: FRP TCP
│   │   └── Allocated via frp-primary (round-robin token 1)
│   │   └── public_endpoint: tcp://frp.example.com:31337
│   ├── Export 2: ngrok HTTP
│   │   └── Allocated via ngrok-account-2 (fallback when account-1 exhausted)
│   │   └── public_endpoint: https://abc123.ngrok.io
│   └── Export 3: Rathole TCP (backup)
│       └── Allocated via rathole-server-2 (round-robin)
│       └── public_endpoint: tcp://rathole.example.com:5300
```

**Key Points:**
- Multiple exports per runtime allow redundancy
- Each export uses its own token/server via rotation strategy
- If one provider fails, user still has other endpoints
- Automatic failover: if FRP hits limit, ngrok takes over
- Clean abstraction: infrastructure layer handles token selection

## Database Schema (MVP - 3 Tables)

### `challenges`
Challenge registry from repository path.

```sql
CREATE TABLE challenges (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    service_port INTEGER NOT NULL,
    service_type TEXT DEFAULT 'http',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Fields:
- `id`: Primary key
- `name`: Challenge identifier (e.g., "web/sqli-basic")
- `path`: Repository path relative to repo root
- `service_port`: Internal container port (8080, 22, 31337, etc.)
- `service_type`: "http", "tcp", etc.
- `enabled`: Whether this challenge is active
- `created_at`: Registration timestamp

### `runtime_instances`
Active or stopped runtime containers.

```sql
CREATE TABLE runtime_instances (
    id INTEGER PRIMARY KEY,
    challenge_id INTEGER NOT NULL,
    status TEXT DEFAULT 'stopped',
    container_id TEXT,
    tunnel_provider TEXT,
    public_url TEXT,
    started_at TIMESTAMP,
    expires_at TIMESTAMP,
    last_activity TIMESTAMP,
    last_revert TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (challenge_id) REFERENCES challenges(id)
);
```

Fields:
- `id`: Primary key
- `challenge_id`: Foreign key to challenges
- `status`: "running", "stopped", "error"
- `container_id`: Docker container ID
- `tunnel_provider`: Primary tunnel provider in use
- `public_url`: Main public URL if exposed
- `started_at`: When container was started
- `expires_at`: TTL expiration timestamp
- `last_activity`: Last access time (for idle detection)
- `last_revert`: Last revert time (for cooldown enforcement)

### `challenge_exports`
Multiple export/tunnel bindings per runtime.

```sql
CREATE TABLE challenge_exports (
    id INTEGER PRIMARY KEY,
    runtime_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    protocol TEXT,
    target_port INTEGER,
    public_endpoint TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (runtime_id) REFERENCES runtime_instances(id)
);
```

Fields:
- `id`: Primary key
- `runtime_id`: Foreign key to runtime_instances
- `provider`: "frp", "cloudflare", "ngrok", etc.
- `protocol`: "http", "tcp"
- `target_port`: Container port this export targets
- `public_endpoint`: Public URL/endpoint (e.g., "abc.ngrok.io", "tcp://1.1.1.1:31337")
- `status`: "active", "creating", "failed"

## MVP Configuration

**Single Global Config File** (`config.yml`)

```yaml
# Repository Configuration
github_repo: https://github.com/org/ctf-challenges
branch: main
access_token: ${GITHUB_TOKEN}

# Cache and Build Directories
cache_dir: ./data/cache
build_dir: ./data/build
db_file: ./data/ctf-orch.db

# Default Tunnel Provider
default_tunnel: frp

# Runtime Behavior
idle_timeout_minutes: 15
revert_cooldown_minutes: 5
max_runtime_hours: 2

# Tunnel Providers Configuration
tunnels:
  frp:
    enabled: true
    type: self-hosted
    server_addr: localhost
    server_port: 7000

  cloudflare:
    enabled: false
    token: ${CLOUDFLARE_TOKEN}

  ngrok:
    enabled: false
    token: ${NGROK_TOKEN}
```

**Key Design Decisions:**
- **Single Repository Source**: All challenges live in one repo under different paths
- **No Multi-Repo Sync**: Simpler, faster, cleaner credential management
- **No Webhook Complexity**: Manual sync or polling is sufficient for MVP
- **Environment Variables**: Secrets passed via env, not in config file

## Recommended Stack For MVP
- Language: Python
- CLI: Typer or Click
- Config and validation: Pydantic
- State store: PostgreSQL for production, SQLite for local MVP
- Cache metadata: SQLite or Postgres tables
- Job queue: Redis + RQ or Celery
- Docker integration: Docker SDK for Python
- Git sync: GitPython or direct Git CLI wrapper
- Tunnel abstraction: provider interface with pluggable adapters
- Monitoring: structured logs + Prometheus later

## Language Recommendation
### MVP
Use Python because:
- current repo is already Python
- fastest path to stable CLI and orchestration engine
- mature Docker, Git, queue, and validation libraries
- easier incremental migration from existing HPone codebase

### Longer Term
If throughput and concurrency become dominant concerns, migrate the core worker and control plane to Go, while keeping the CLI and config layer compatible.

## Docker vs Kubernetes
### Recommendation For MVP
Use Docker + Compose first.

Why:
- simpler lifecycle handling
- lower operational cost
- better fit for single-node or small-cluster deployments
- easier shared runtime control and image reuse

### When Kubernetes Becomes Worth It
Move to Kubernetes only if you need:
- multi-node scheduling at scale
- strict workload isolation per challenge class
- automatic node-level rescheduling
- advanced network policy and tenancy management

For the current problem, Kubernetes is overkill for MVP and adds unnecessary complexity.

## Tunnel Token Management (MVP)

One of the key MVP features is **multi-token support** for scalability without vendor lock-in.

### Why Multi-Token?
- **Rate Limits**: Free services like ngrok limit tunnel count per account
- **Team Usage**: Multiple team members need concurrent tunnels
- **Cost Distribution**: Spread usage across multiple accounts to avoid overages
- **Failover**: Automatic fallback when token hits limit or becomes invalid
- **Flexibility**: Easy to rotate tokens when one account is exhausted

### Token Rotation Strategies

#### 1. Round-Robin
Distributes new tunnels evenly across all available tokens.
```
Tunnel 1 → Account A
Tunnel 2 → Account B
Tunnel 3 → Account C
Tunnel 4 → Account A (round back)
```

Good for:
- Load balancing
- Even distribution of quota usage
- Team environments with multiple accounts

#### 2. Fallback
Uses tokens in order, moves to next on error.
```
Try Account A
  → Error/limit exceeded
Try Account B
  → Success
```

Good for:
- High availability
- Automatic failover
- Hybrid setups (primary + backup)

### Implementation in Provider Interface

```python
class TunnelProvider:
    def __init__(self, config):
        self.tokens = config['tokens']  # or 'servers'
        self.rotation_strategy = config['rotation_strategy']
        self.current_index = 0

    def allocate_tunnel(self, challenge_id, port):
        """Allocate tunnel using rotation strategy."""
        if self.rotation_strategy == 'round-robin':
            token = self.tokens[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.tokens)
        elif self.rotation_strategy == 'fallback':
            token = self._find_available_token()

        return self.create_tunnel(token, port)

    def _find_available_token(self):
        """Find token that hasn't hit limit."""
        for token in self.tokens:
            if not self._is_token_exhausted(token):
                return token
        # All tokens exhausted, use first one anyway
        return self.tokens[0]
```

### Token Usage Tracking

**Optional: Track token usage per challenge_exports row**

```sql
ALTER TABLE challenge_exports ADD COLUMN (
    token_name TEXT,        -- which token was used
    created_via_token_id INT -- for audit/usage tracking
);
```

This allows later:
- Usage analytics per token
- Proactive token rotation
- Cost attribution per challenge
- run containers as non-root where possible
- apply seccomp and AppArmor profiles
- limit capabilities
- set memory and CPU quotas
- isolate network namespaces
- disable privileged mode by default
- sanitize mounted volumes
- keep challenge source read-only at runtime when possible
- record audit logs for admin actions

## Deployment Topology
### Single Node MVP
- CLI on admin workstation or control host
- orchestration engine on one server
- PostgreSQL or SQLite for state
- Redis for queue if asynchronous jobs are enabled
- Docker Engine on same host
- tunnel provider process or external tunnel service

### Multi Node Future
- control plane API
- worker nodes register via heartbeat
- scheduler assigns challenge runtime placement
- shared registry and state store
- distributed cache or node-local source mirrors

## Project Structure (MVP)

```text
ctf-orchestration/
├── app.py                    # CLI entry point
├── config.yml                # Global configuration
├── README.md
├── docs/
│   └── ctf-orchestrator-architecture.md
├── src/                      # Source code
│   ├── __init__.py
│   ├── cli/                  # Command handlers
│   │   └── __init__.py
│   ├── domain/               # Core models (Challenge, RuntimeInstance, Export)
│   │   └── __init__.py
│   ├── services/             # Business logic (sync, build, runtime management)
│   │   └── __init__.py
│   └── infrastructure/       # Adapters (Docker, Git, DB, Tunnel providers)
│       └── __init__.py
└── data/                     # Runtime data directory
    ├── cache/                # Git clones, source mirrors
    ├── build/                # Built Docker images metadata
    └── ctf-orch.db          # SQLite state database
```

**Design Notes:**
- `app.py` at root is the only entry point
- `config.yml` is single source of config
- `src/` contains all Python modules
- `data/` contains runtime artifacts and state
- Clear separation: CLI → Services → Infrastructure

## MVP Milestones
1. Define challenge metadata and registry schema.
2. Implement repo sync and local cache.
3. Implement build and image tagging pipeline.
4. Implement shared runtime start/stop/restart/revert.
5. Implement idle detection and health checks.
6. Implement tunnel abstraction and public URL generation.
7. Add CLI commands and state inspection.
8. Add worker queue and event handling.
