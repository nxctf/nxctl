# Tunnel Providers Guide - Hosted Only

This guide covers **Hosted Tunnel Providers** - services that provide tunneling infrastructure for FREE, with NO setup required and NO need for public IP.

All providers listed here have their own relay servers and public infrastructure, so you can use them immediately.

## Why Hosted Providers?

- **No Infrastructure Setup**: No need to run your own servers
- **Free Tier Available**: All options have generous free plans
- **No Public IP Required**: Works behind NAT/firewalls
- **Instant Activation**: Get public URLs immediately
- **Easy Multi-Token**: Scale by adding more accounts/tokens

## Supported Providers

### 1. ngrok - Fast & Reliable

**Website:** https://ngrok.com

**Best for:** Professional setup, custom domains, multiple concurrent tunnels

**Pricing:**
- Free tier: 4 concurrent tunnels, 40 req/min per tunnel
- Pro: Unlimited tunnels, 200 req/min per tunnel
- Enterprise: Custom options

**Setup:**

```bash
# 1. Sign up at https://ngrok.com
# 2. Get your auth token at https://dashboard.ngrok.com/get-started/your-authtoken
# 3. Set environment variable
export NGROK_TOKEN_1=your-token-here

# 4. Install ngrok CLI (optional, we'll use API)
# Download from https://ngrok.com/download
```

**config.yml:**

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
```

**Public URL Example:**
```
http://12345abc.ngrok.io
```

---

### 2. localtunnel - Zero Configuration

**Website:** https://localtunnel.me

**Best for:** Quick testing, no account needed, random URLs

**Pricing:**
- Completely free
- Unlimited tunnels
- Unlimited bandwidth
- Unlimited requests

**Setup:**

```bash
# Zero setup! Just use it
# No token, no account, nothing
# Pick a random subdomain name or leave empty for auto-generated
```

**config.yml:**

```yaml
tunnels:
  localtunnel:
    enabled: true
    rotation_strategy: round-robin
    subdomains:
      - ""  # Auto-generate random subdomain
      # Or specify custom names (first-come, first-served):
      # - "ctf-web-001"
      # - "ctf-crypto-001"
      # - "ctf-pwn-001"
```

**Public URL Example:**
```
https://ctf-web-001.loca.lt
https://randomly-named-12345.loca.lt
```

**Advantage:**
- No account required
- No token needed
- Just start using immediately

---

### 3. serveo - SSH-Based Tunneling

**Website:** https://serveo.net

**Best for:** Simple HTTP tunneling, direct URL sharing

**Pricing:**
- Completely free
- No account required
- Unlimited tunnels
- Minimal setup

**Setup:**

```bash
# SSH-based tunneling (optional, for advanced use)
# ssh -R 80:localhost:8080 serveo.net

# OR just use the HTTP endpoint:
# No account needed, direct HTTP forward
```

**config.yml:**

```yaml
tunnels:
  serveo:
    enabled: true
    rotation_strategy: round-robin
    # No tokens needed - auto-generates URLs
```

**Public URL Example:**
```
https://uniquename-12345.serveo.net
```

**Advantage:**
- Supports SSH reverse proxy
- Custom subdomains available
- Direct HTTPS support

---

### 4. pinggy - Short & Simple

**Website:** https://pinggy.io

**Best for:** Ultra-simple setup, short URLs, minimal config

**Pricing:**
- Free tier: 2 concurrent tunnels
- Pro: Unlimited tunnels, $4/month
- Enterprise: Custom

**Setup:**

```bash
# Zero config - just get a token or use free mode
# Sign up at https://pinggy.io for free tier
# Get short URLs like: https://q1w2e3r4.pinggy.io
```

**config.yml:**

```yaml
tunnels:
  pinggy:
    enabled: true
    rotation_strategy: round-robin
    # Free tier: auto-generates URLs
```

**Public URL Example:**
```
https://q1w2e3r4t5y6u7i8.pinggy.io
```

---

## Quick Comparison

| Provider | Free Tier | Setup | Token Needed | Bandwidth | Domains |
|----------|-----------|-------|--------------|-----------|---------|
| **ngrok** | 4 tunnels | 5 min | Yes | Limited | Custom |
| **localtunnel** | Unlimited | 0 min | No | Unlimited | Random |
| **serveo** | Unlimited | 0 min | No | Unlimited | Custom |
| **pinggy** | 2 tunnels | 5 min | Optional | Unlimited | Random |

## Multi-Token Strategy

When you hit rate limits on one provider:

```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin
    tokens:
      - name: "account-1"
        token: ${NGROK_TOKEN_1}
        region: us
      - name: "account-2"
        token: ${NGROK_TOKEN_2}
        region: eu
      - name: "account-3"
        token: ${NGROK_TOKEN_3}
        region: ap
```

The system will:
- **Round-robin**: Distribute new tunnels evenly across tokens
- **Fallback**: Use next token if current one is exhausted

## Setup Guide

### For ngrok (Recommended for Production)

```bash
# 1. Sign up
# Visit https://ngrok.com and create account

# 2. Get token
# Go to https://dashboard.ngrok.com/get-started/your-authtoken
# Copy your auth token

# 3. Add to config.yml
# tunnels:
#   ngrok:
#     enabled: true
#     tokens:
#       - name: "ngrok-1"
#         token: 1BtXxxxxxxxxxxxxxxxxxxxxx
#         region: us

# 4. Test
python app.py challenge sync  # This will test connection
```

### For localtunnel (Quick Testing)

```bash
# 1. No account needed!

# 2. Just update config.yml
# tunnels:
#   localtunnel:
#     enabled: true
#     subdomains:
#       - ""  # auto-generate

# 3. Start using immediately
python app.py challenge sync
```

## Configuration Examples

### Single ngrok account

```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin
    tokens:
      - name: "account-1"
        token: ${NGROK_TOKEN_1}
        region: us
```

### Multiple ngrok accounts (load balancing)

```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin
    tokens:
      - name: "account-us"
        token: ${NGROK_TOKEN_US}
        region: us
      - name: "account-eu"
        token: ${NGROK_TOKEN_EU}
        region: eu
      - name: "account-ap"
        token: ${NGROK_TOKEN_AP}
        region: ap
```

### Mix of providers

```yaml
tunnels:
  # Primary: ngrok (paid, reliable)
  ngrok:
    enabled: true
    rotation_strategy: fallback
    tokens:
      - name: "ngrok-primary"
        token: ${NGROK_TOKEN_1}
        region: us
      - name: "ngrok-fallback"
        token: ${NGROK_TOKEN_2}
        region: eu

  # Secondary: localtunnel (free backup)
  localtunnel:
    enabled: true
    rotation_strategy: round-robin
    subdomains:
      - ""
```

## Monitoring Tunnel Usage

Check which tunnels are being used:

```bash
# View all tunnels created
sqlite3 data/ctf-orch.db "
SELECT
  runtime_id,
  provider,
  public_endpoint,
  status,
  created_at
FROM challenge_exports
WHERE created_at > datetime('now', '-1 hour')
ORDER BY created_at DESC;
"
```

This shows:
- Which provider each challenge is using
- Public endpoint (URL)
- When it was created

## Troubleshooting

### "Invalid token" error
- Check token is correct at provider dashboard
- Verify token is set in environment variable
- Make sure YAML syntax is correct

### "Connection refused"
- Check internet connection
- Verify provider is not down (check status page)
- Try different provider

### "No available tokens"
- All tokens are exhausted or invalid
- Add more accounts/tokens to rotation
- Wait for connections to expire
- Check token limits at provider dashboard

### "Rate limited"
- Single token hit its rate limit
- Add more tokens via multi-token config
- Switch to different provider with higher limits

## Environment Variables

Set in shell or `.env` file:

```bash
# ngrok tokens
export NGROK_TOKEN_1="your-token-1"
export NGROK_TOKEN_2="your-token-2"
export NGROK_TOKEN_3="your-token-3"

# localtunnel, serveo, pinggy
# No environment variables needed!
```

## Recommended Setup for CTF

**Small Event (< 10 challenges):**
```yaml
tunnels:
  localtunnel:
    enabled: true  # Free, unlimited
```

**Medium Event (10-50 challenges):**
```yaml
tunnels:
  ngrok:
    enabled: true
    tokens:
      - token: ${NGROK_TOKEN_1}
        region: us
  localtunnel:
    enabled: true  # Fallback
```

**Large Event (> 50 challenges):**
```yaml
tunnels:
  ngrok:
    enabled: true
    rotation_strategy: round-robin
    tokens:
      - token: ${NGROK_TOKEN_1}
        region: us
      - token: ${NGROK_TOKEN_2}
        region: eu
      - token: ${NGROK_TOKEN_3}
        region: ap
  localtunnel:
    enabled: true  # Fallback
```

## Next Steps

1. Choose a provider (ngrok for production, localtunnel for testing)
2. Get credentials if needed
3. Update `config.yml`
4. Test with `python app.py challenge sync`
5. Monitor usage via database queries
6. Scale by adding more tokens/accounts as needed
