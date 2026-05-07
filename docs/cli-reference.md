# CLI Quick Reference

## Installation & Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and configure
cp config.example.yml config.yml
cp .env.example .env

# 3. Edit config.yml with your repository
# 4. Set environment variables in .env or shell

# 5. Run a command
python app.py challenge sync
```

## Challenge Commands

### Sync challenges from repository
```bash
python app.py challenge sync
```
Clones/updates the Git repository and discovers all challenges.
- Creates database tables
- Clones repository (cached)
- Scans for Dockerfile/docker-compose.yml
- Extracts port and service type
- Saves to database

### List all challenges
```bash
python app.py challenge list
```
Shows all discovered challenges in a table.

### Inspect specific challenge
```bash
python app.py challenge inspect web/sqli-basic
```
Shows detailed information about a challenge.

## Configuration

### config.yml structure

```yaml
# Repository source
github_repo: https://github.com/org/ctf-challenges
branch: main
access_token: ${GITHUB_TOKEN}

# Paths
cache_dir: ./data/cache
build_dir: ./data/build
db_file: ./data/ctf-orch.db

# Runtime behavior
idle_timeout_minutes: 15
revert_cooldown_minutes: 5
max_runtime_hours: 2

# Default tunnel provider
default_tunnel: frp

# Tunnel providers (see docs/tunnel-providers-guide.md)
tunnels:
  frp:
    enabled: true
    rotation_strategy: round-robin
    servers:
      - name: "frp-primary"
        server_addr: localhost
        server_port: 7000
        token: ${FRP_TOKEN_PRIMARY}
```

## Environment Variables

Set in shell or `.env` file:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
export FRP_TOKEN_PRIMARY=your-token
export NGROK_TOKEN_1=your-ngrok-token
```

## Database

SQLite database at path specified in config.yml (default: `./data/ctf-orch.db`)

### Tables

**challenges**
- id, name, path, service_port, service_type, enabled, created_at

**runtime_instances**
- id, challenge_id, status, container_id, tunnel_provider, public_url, ...

**challenge_exports**
- id, runtime_id, provider, protocol, target_port, public_endpoint, status, created_at

### Query examples

```bash
# List all challenges
sqlite3 data/ctf-orch.db "SELECT name, path, service_port FROM challenges;"

# Clear all challenges (for resync)
sqlite3 data/ctf-orch.db "DELETE FROM challenges;"

# View runtime status
sqlite3 data/ctf-orch.db "SELECT * FROM runtime_instances;"
```

## Directory Structure

```
data/
├── cache/              # Git repository clones
├── build/              # Build artifacts (images metadata)
└── ctf-orch.db        # SQLite database

src/
├── cli/                # CLI command handlers
├── domain/             # Data models
├── services/           # Business logic
└── infrastructure/     # Config, DB, Git adapters
```

## Common Issues

### Git clone fails
- Verify `github_repo` URL
- Check `GITHUB_TOKEN` is set for private repos
- Verify network connectivity

### No challenges found
- Check repository has proper structure: `category/challenge-name/Dockerfile`
- Run `challenge sync` again
- Check database: `sqlite3 data/ctf-orch.db "SELECT * FROM challenges;"`

### Port conflicts
- Different challenges use different ports
- Check `sqlite3 data/ctf-orch.db "SELECT name, service_port FROM challenges;"`

## Next Steps

After verifying sync works:
1. Implement Docker build service
2. Implement runtime start/stop commands
3. Implement tunnel provider abstractions
4. Add activity tracking and idle detection
