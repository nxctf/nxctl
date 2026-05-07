# Testing the CTF Orchestration Engine

## Prerequisites

Before testing, install Python dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy the example config and edit it with your repository details:

```bash
cp config.example.yml config.yml
```

Edit `config.yml` with your GitHub repository:

```yaml
# Example config
github_repo: https://github.com/org/ctf-challenges
branch: main
access_token: ${GITHUB_TOKEN}  # Optional, only needed for private repos

cache_dir: ./data/cache
build_dir: ./data/build
db_file: ./data/ctf-orch.db

default_tunnel: localtunnel  # Hosted provider, no setup needed

idle_timeout_minutes: 15
revert_cooldown_minutes: 5
max_runtime_hours: 2

tunnels:
  localtunnel:
    enabled: true
    rotation_strategy: round-robin
    subdomains:
      - ""  # Auto-generate
```

## Environment Variables (Optional)

GitHub token is only needed for **private repositories**:

```bash
# Linux/Mac
export GITHUB_TOKEN=your-github-token-here

# Windows PowerShell
$env:GITHUB_TOKEN="your-github-token-here"
```

## How Clone Works

The system uses a **smart fallback strategy**:

1. **First attempt**: Clone without token (for public repositories)
   - Fast, no credentials needed
   - Works for all public GitHub repos

2. **If auth fails**: Automatically retry with token (for private repositories)
   - Detects authentication errors automatically
   - Uses token if provided in config/env

3. **If both fail**: Reports error with helpful message

**Result:**
- ✅ Public repos work immediately (no token needed)
- ✅ Private repos use token automatically when needed
- ✅ No need to manually specify public vs private

## Test Challenge Sync

First, test syncing challenges from your repository:

```bash
python app.py challenge sync
```

Expected output:
```
[INFO] Syncing challenges from https://github.com/org/ctf-challenges
[INFO] Repository cloned successfully
[INFO] Discovered challenge: web/sqli-basic (port 8080, type http)
[INFO] Discovered challenge: crypto/rsa-101 (port 9000, type tcp)
[INFO] Synced 2 challenges

✓ Synced 2 challenges from repository
  • web/sqli-basic (port 8080, type http)
  • crypto/rsa-101 (port 9000, type tcp)
```

## Test Challenge List

List all synced challenges:

```bash
python app.py challenge list
```

Expected output:
```
Total: 2 challenges

Name                          | Port | Type   | Path
----------------------------------------------------------------------
crypto/rsa-101                | 9000 | tcp    | crypto/rsa-101
web/sqli-basic                | 8080 | http   | web/sqli-basic
```

## Test Challenge Inspect

Get details about a specific challenge:

```bash
python app.py challenge inspect web/sqli-basic
```

Expected output:
```
Challenge: web/sqli-basic
  Path:        web/sqli-basic
  Port:        8080
  Type:        http
  Enabled:     Yes
  Created:     2026-05-07 10:30:45.123456
```

## Troubleshooting

### "Config file not found"
- Make sure you created `config.yml` from `config.example.yml`
- Check the file is in the project root directory

### "Git clone failed"
- Verify `github_repo` URL in config.yml
- If repository is private, set `GITHUB_TOKEN` environment variable
- Check your network connection

### "No Dockerfile or docker-compose.yml found"
- Challenges must have `Dockerfile` OR `docker-compose.yml`
- Check repository structure

### "Token exhausted" (later, after implementing tunnels)
- Configure multiple tokens in tunnels section
- Check token validity in environment variables

## Next Steps

After successful sync and list, next features to implement:

1. **Docker Build** - Build challenge images from Dockerfile
2. **Runtime Start/Stop** - Docker compose lifecycle management
3. **Tunnel Management** - FRP/ngrok/rathole tunnel creation
4. **Activity Tracking** - Track last access time for idle detection
5. **Revert Logic** - Clean state restoration with cooldown

## Database Inspection

View challenges in database:

```bash
sqlite3 data/ctf-orch.db "SELECT * FROM challenges;"
```

View runtime instances:

```bash
sqlite3 data/ctf-orch.db "SELECT * FROM runtime_instances;"
```

View exports:

```bash
sqlite3 data/ctf-orch.db "SELECT * FROM challenge_exports;"
```
