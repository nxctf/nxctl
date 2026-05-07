# CTF Challenge Orchestration Engine

A lightweight, CLI-first container orchestration platform for CTF challenges.

## Features

- **Single Repository Source**: All challenges from one Git repo, organized by path
- **Shared Runtime Instances**: Challenges are shared across users, not one per user
- **Fast Startup**: Prebuilt images and local caching for instant challenge starts
- **Multiple Export Providers**: FRP, Cloudflare Tunnel, ngrok on same runtime
- **Idle Cleanup**: Auto-shutdown after 15 minutes of inactivity
- **Revert with Cooldown**: Restore challenges to clean state safely
- **Simple Database**: 3 tables (challenges, runtime_instances, challenge_exports)
- **CLI-First Design**: API and web dashboard can come later

## Quick Architecture

```yaml
config.yml          # 1 global config
  ↓
github repo         # 1 repository source
  ↓
challenges (DB)     # Challenge registry
  ↓
runtime_instances   # Running containers
  ↓
challenge_exports   # Public URLs (multiple per runtime)
```

## Quick Start

### Installation

```bash
# Clone this repository
git clone <this-repo>
cd ctf-orchestration

# Install Python dependencies
pip install -r requirements.txt

# Configure
cp config.example.yml config.yml
# Edit config.yml with your GitHub token and repo
```

### Usage

```bash
# Sync challenges from repository
python app.py challenge sync

# List all challenges
python app.py challenge list

# Start a challenge
python app.py runtime start web/sqli-basic

# Get public URL
python app.py export url web/sqli-basic

# Stop challenge
python app.py runtime stop web/sqli-basic

# Revert to clean state
python app.py runtime revert web/sqli-basic
```

## Architecture

Full architecture documentation: [docs/ctf-orchestrator-architecture.md](docs/ctf-orchestrator-architecture.md)

### Key Concepts

**Challenges**: Stored in one Git repo under different paths
```
challenges/
├── web/
│   ├── sqli-basic/
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   └── xss-advanced/
├── crypto/
│   └── rsa-101/
└── pwn/
    └── buffer-overflow/
```

**Runtime**: Single container instance shared by all users
```
Challenge web/sqli-basic
├── Container: abc123xyz
├── Exports:
│   ├── FRP TCP: tcp://attacker.com:31337
│   ├── Cloudflare HTTP: https://sqli.ctf.lab
│   └── ngrok: https://abc123.ngrok.io
```

**Lifecycle**: Simple state transitions
```
stopped → running → {idle → stopped | revert → running}
```

## Database Schema

**challenges** - Challenge registry
```sql
id, name, path, service_port, service_type, enabled, created_at
```

**runtime_instances** - Active/stopped runtimes
```sql
id, challenge_id, status, container_id, tunnel_provider, public_url,
started_at, expires_at, last_activity, last_revert, created_at
```

**challenge_exports** - Multiple exports per runtime
```sql
id, runtime_id, provider, protocol, target_port, public_endpoint, status, created_at
```

## Configuration

Global config file: `config.yml`

```yaml
# Repository
github_repo: https://github.com/org/ctf-challenges
branch: main
access_token: ${GITHUB_TOKEN}

# Paths
cache_dir: ./data/cache
build_dir: ./data/build
db_file: ./data/ctf-orch.db

# Behavior
idle_timeout_minutes: 15
revert_cooldown_minutes: 5
max_runtime_hours: 2

# Tunnel Providers (with multi-token support)
tunnels:
  frp:
    enabled: true
    rotation_strategy: round-robin  # or fallback
    servers:
      - name: "frp-primary"
        server_addr: frp1.example.com
        server_port: 7000
        token: ${FRP_TOKEN_PRIMARY}
      - name: "frp-secondary"  # Failover/load balancing
        server_addr: frp2.example.com
        server_port: 7000
        token: ${FRP_TOKEN_SECONDARY}

  ngrok:
    enabled: false
    rotation_strategy: round-robin
    tokens:
      - name: "ngrok-account-1"
        token: ${NGROK_TOKEN_1}
        region: us
      - name: "ngrok-account-2"  # Token rotation for free tier
        token: ${NGROK_TOKEN_2}
        region: eu

  rathole:
    enabled: false
    rotation_strategy: round-robin
    servers:
      - name: "rathole-main"
        server_addr: rathole.example.com
        server_port: 5202
        token: ${RATHOLE_TOKEN}
```

**Multi-Token Strategy:**
- Support multiple tokens/servers per provider
- Automatic rotation when token limits are reached
- Failover for high availability
- Round-robin or fallback strategies
- See [Tunnel Providers Guide](docs/tunnel-providers-guide.md) for detailed setup

## Project Structure

```
.
├── app.py                    # CLI entry point
├── config.yml                # Global configuration
├── config.example.yml        # Config template
├── requirements.txt          # Python dependencies
├── docs/
│   └── ctf-orchestrator-architecture.md
├── src/                      # Source code
│   ├── __init__.py
│   ├── cli/                  # CLI command handlers
│   ├── domain/               # Core models
│   ├── services/             # Business logic
│   └── infrastructure/       # External adapters
├── data/                     # Runtime artifacts
│   ├── cache/                # Git clones
│   ├── build/                # Build artifacts
│   └── ctf-orch.db          # SQLite database
├── tests/                    # Test suite
├── HPone/                    # Reference: Honeypot manager (separate project)
└── README.md                 # This file
```

## Next Steps

1. **Foundation**: Set up database schema and config loader
2. **Git Sync**: Implement repository sync and challenge discovery
3. **Docker**: Implement build and container lifecycle
4. **Runtime**: Implement start/stop/restart/revert logic
5. **Tunnels**: Implement tunnel provider abstractions
6. **CLI**: Build command handlers and CLI wiring
7. **Worker**: Implement background idle detection
8. **Testing**: Add test coverage
9. **API**: Wrap CLI with REST API (later)
10. **Web**: Build web dashboard (later)

## Why This Design?

- **Simple**: 3 database tables, 1 config file, 1 repo
- **Scalable**: Easy to add providers, services, commands
- **Maintainable**: Clear separation of concerns (CLI → Services → Infrastructure)
- **Testable**: Each layer is independently testable
- **Extensible**: Provider interfaces allow swapping implementations

## References

- [CTF Orchestrator Architecture Docs](docs/ctf-orchestrator-architecture.md) - Complete architecture design
- [Tunnel Providers Guide](docs/tunnel-providers-guide.md) - Multi-token setup and provider comparison
- [HPone Honeypot Manager](HPone/) - Reference Docker manager (separate project)

## License

To be determined.
