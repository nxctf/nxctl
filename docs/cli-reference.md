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
- **Smart Clone**: Tries public clone first, auto-retries with token if needed
- Creates database tables if needed
- Clones/updates repository (cached locally)
- Scans for Dockerfile/docker-compose.yml
- Extracts port and service type from docker-compose.yml
- Saves to database

✅ Works with public repos (no token needed)
✅ Works with private repos (auto-uses token if provided)

### List all challenges
```bash
python app.py challenge list
```
Shows all discovered challenges in a table with port and type.

### Inspect specific challenge
```bash
python app.py challenge inspect <name>
```
Shows detailed information about a single challenge.

Example:
```bash
python app.py challenge inspect web/sqli-basic
```

### Add a challenge manually
```bash
python app.py challenge add <name> <path> <port> [--type http|tcp]
```
Add a challenge without syncing from repo.

Example:
```bash
python app.py challenge add web/custom-web web/custom-web 9000 --type http
```

### Remove a challenge
```bash
python app.py challenge remove <name>
```
Delete a challenge from database.

### Enable/Disable challenges
```bash
python app.py challenge enable <name>
python app.py challenge disable <name>
```
Enable or disable a challenge (soft delete, doesn't remove from DB).

## Git Clone Behavior

The system uses **smart clone strategy** for handling public and private repositories:

### How it works
1. **First attempt**: Clone without token
   - No credentials needed
   - Fast, works for public repos

2. **If authentication fails**: Automatically retry with token
   - Detects auth errors (permission denied, not found, etc.)
   - Uses token from config/environment variable

3. **Result**:
   - Public repos: Work immediately ✅
   - Private repos: Auto-use token when needed ✅
   - No manual setup required ✅

### Example
```bash
# Works for public repos (no token needed)
python app.py challenge sync

# Also works for private repos (auto-uses token from config/env)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
python app.py challenge sync
```

## Configuration

### config.yml structure

```yaml
# Repository source (works with public AND private repos)
github_repo: https://github.com/org/ctf-challenges
branch: main
access_token: ${GITHUB_TOKEN}  # Only needed for private repos

# Paths
cache_dir: ./data/cache
build_dir: ./data/build
db_file: ./data/ctf-orch.db

# Runtime behavior
idle_timeout_minutes: 15
revert_cooldown_minutes: 5
max_runtime_hours: 2

# Default tunnel provider
default_tunnel: localtunnel  # Hosted provider, no setup needed

# Tunnel providers (see docs/tunnel-providers-guide.md)
tunnels:
  localtunnel:
    enabled: true
    rotation_strategy: round-robin
    subdomains:
      - ""  # Auto-generate
```

## Environment Variables

Set in shell or `.env` file:

```bash
# GitHub token - only needed for private repos
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Tunnel provider tokens (if using paid plans)
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

### Git clone fails with "authentication failed"
- For public repos: Should work automatically, check network
- For private repos: Set GITHUB_TOKEN environment variable
- The system tries public clone first, then auto-retries with token

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
