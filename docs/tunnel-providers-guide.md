# Tunnel Providers Configuration Guide

This guide explains how to configure multiple tunnel providers with multi-token support for scalability and failover.

## Why Multiple Tokens?

When running CTF challenges for teams or events, single-token providers hit rate limits:
- **ngrok free**: Limited concurrent tunnels per account
- **FRP**: Single server can become bottleneck
- **Rathole**: Better to distribute across multiple servers

Solution: Configure multiple tokens/servers per provider.

## Providers Overview

### 1. FRP (Self-Hosted Reverse Proxy)

**Best for:** Full control, TCP + HTTP, self-hosted infrastructure

**Setup:**
```bash
# Install FRP server
wget https://github.com/fatedier/frp/releases/download/v0.52.0/frp_0.52.0_linux_amd64.tar.gz
tar xzf frp_0.52.0_linux_amd64.tar.gz
cd frp_0.52.0_linux_amd64

# Start FRP server
./frps -c frps.toml
```

**Config (single server):**
```yaml
tunnels:
  frp:
    enabled: true
    rotation_strategy: round-robin
    servers:
      - name: "frp-primary"
        server_addr: frp1.example.com
        server_port: 7000
        token: your-frp-token
```

**Config (failover setup):**
```yaml
tunnels:
  frp:
    enabled: true
    rotation_strategy: fallback  # Try primary, fallback to secondary
    servers:
      - name: "frp-primary"
        server_addr: frp1.example.com
        server_port: 7000
        token: ${FRP_TOKEN_PRIMARY}
      - name: "frp-secondary"
        server_addr: frp2.example.com
        server_port: 7000
        token: ${FRP_TOKEN_SECONDARY}
```

### 2. ngrok (Public Tunneling Service)

**Best for:** Quick setup, no self-hosting, automatic public URLs

**Setup:**
```bash
# Download ngrok
curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt update && sudo apt install ngrok

# Or download binary from https://ngrok.com/download
```

**Config (single account):**
```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin
    tokens:
      - name: "ngrok-team-1"
        token: ${NGROK_TOKEN_1}
        region: us
```

**Config (multi-account rotation):**
```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin  # Distribute across accounts
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
```

**Get tokens from:**
```bash
# Sign up at https://ngrok.com
# Find your token at https://dashboard.ngrok.com/get-started/your-authtoken

# Or export multiple tokens as env vars
export NGROK_TOKEN_1=<your-first-token>
export NGROK_TOKEN_2=<your-second-token>
export NGROK_TOKEN_3=<your-third-token>
```

### 3. Rathole (Lightweight P2P Reverse Proxy)

**Best for:** Low-resource deployments, P2P, self-hosted

**Setup:**
```bash
# Download rathole
git clone https://github.com/rapiz1/rathole.git
cd rathole
cargo build --release

# Start server
./target/release/rathole server.toml
```

**Config:**
```yaml
tunnels:
  rathole:
    enabled: true
    rotation_strategy: round-robin
    servers:
      - name: "rathole-main"
        server_addr: rathole.example.com
        server_port: 5202
        token: ${RATHOLE_TOKEN_1}
      - name: "rathole-backup"
        server_addr: rathole-backup.example.com
        server_port: 5202
        token: ${RATHOLE_TOKEN_2}
```

## Setting Up Environment Variables

Use `.env` file for sensitive tokens:

```bash
# .env
FRP_TOKEN_PRIMARY=frp-token-here
FRP_TOKEN_SECONDARY=frp-backup-token-here

NGROK_TOKEN_1=ngrok-token-1
NGROK_TOKEN_2=ngrok-token-2
NGROK_TOKEN_3=ngrok-token-3

RATHOLE_TOKEN_1=rathole-token-1
RATHOLE_TOKEN_2=rathole-token-2
```

Then in `config.yml`:
```yaml
tunnels:
  frp:
    servers:
      - name: "frp-primary"
        server_addr: frp1.example.com
        server_port: 7000
        token: ${FRP_TOKEN_PRIMARY}
```

## Rotation Strategies

### Round-Robin (Load Balancing)
```
Challenge 1 → ngrok-account-1
Challenge 2 → ngrok-account-2
Challenge 3 → ngrok-account-3
Challenge 4 → ngrok-account-1 (wraps around)
```

**Use when:**
- Distributing load evenly
- All tokens have similar quota
- Want predictable token usage

### Fallback (High Availability)
```
Challenge 1 → Try ngrok-account-1
  ✓ Success, use account-1

Challenge 2 → Try ngrok-account-1
  ✗ Rate limited, fallback
  ✓ Use ngrok-account-2
```

**Use when:**
- Primary token is default
- Automatic failover is needed
- Want minimal changes to primary

## Example: Hybrid Setup (Production)

```yaml
tunnels:
  # Primary self-hosted infrastructure
  frp:
    enabled: true
    rotation_strategy: round-robin
    servers:
      - name: "frp-primary"
        server_addr: frp1.internal.com
        server_port: 7000
        token: ${FRP_PRIMARY_TOKEN}
      - name: "frp-secondary"
        server_addr: frp2.internal.com
        server_port: 7000
        token: ${FRP_SECONDARY_TOKEN}

  # Fallback to ngrok for temporary/burst traffic
  ngrok:
    enabled: true
    rotation_strategy: fallback
    tokens:
      - name: "ngrok-burst"
        token: ${NGROK_TOKEN}
        region: us

  # Additional rathole servers
  rathole:
    enabled: true
    rotation_strategy: round-robin
    servers:
      - name: "rathole-1"
        server_addr: rathole1.example.com
        server_port: 5202
        token: ${RATHOLE_TOKEN_1}
      - name: "rathole-2"
        server_addr: rathole2.example.com
        server_port: 5202
        token: ${RATHOLE_TOKEN_2}
```

## Monitoring Token Usage

The `challenge_exports` table tracks which tunnel provider and token is used:

```sql
SELECT
  runtime_id,
  provider,
  public_endpoint,
  created_at
FROM challenge_exports
WHERE created_at > datetime('now', '-1 hour')
GROUP BY provider;
```

This shows:
- How many tunnels per provider
- When tokens might hit limits
- Which provider is busiest

## Troubleshooting

### "Token exhausted" error
- Add more tokens for that provider
- Switch to different provider
- Enable round-robin rotation

### "Connection refused" to tunnel server
- Check server is running: `ps aux | grep frp` / `grep ngrok`
- Check firewall rules
- Verify server address in config

### "No available tokens"
- Check all tokens are still valid
- Check token credentials in env vars
- Regenerate tokens if expired

## Next Steps

1. Choose primary provider (recommend FRP for control)
2. Set up token/credentials
3. Configure in `config.yml`
4. Test with `challenge sync` and `runtime start`
5. Monitor usage and add tokens as needed
