<div align="center">

# NXCTL - CTF Challenge Orchestrator

<p align="center">
  <strong>Modern tooling for running containerized CTF challenges with automated tunnels, TTL controls, and a practical CLI.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Tunneling-Pinggy|Localtunnel|Ngrok-orange?style=for-the-badge" alt="Tunneling">
</p>

</div>

---

## Overview

NXCTF builds modern tools for Capture The Flag (CTF) competitions and cybersecurity training. We focus on creating an ecosystem that makes it easier to build, run, and scale CTF events — from small local competitions to large online challenges.

Our projects are designed with simplicity, performance, and real-world use in mind.

NXCTF is developed openly by the community. Contribute, build challenges, or help shape the ecosystem.

NXCTF is built by the community 🇮🇩 for the global cybersecurity ecosystem.

NXCTL is the command-line orchestrator in the NXCTF ecosystem. It simplifies the lifecycle of containerized challenges, from automated builds and dynamic port assignment to public exposure through Pinggy, Localtunnel, or Ngrok. Its TTL system automatically shuts down expired challenges so event infrastructure stays tidy.

## Key Features

- Docker-native challenge lifecycle management.
- Smart TTL and extension controls.
- Public tunnel support for Pinggy, Localtunnel, and Ngrok.
- Dynamic host-port mapping to avoid conflicts.
- Fast modular CLI for challenge, runtime, and export operations.
- Bash completion for commands and challenge names.
- Optional FastAPI service for remote orchestration.

## Project Structure

```text
nxctl/
|-- setup.sh                    # Interactive installer/uninstaller
|-- nxctl/                      # Main Python package
|   |-- app.py                  # CLI entry point
|   |-- api.py                  # FastAPI app
|   |-- core/                   # Config, Docker, Git, DB, models
|   |-- scripts/                # CLI handlers and service logic
|   `-- completion/             # Bash completion scripts
|-- src/                        # Deprecated compatibility launcher path
|-- data/                       # Persistent data, builds, logs
|-- config.yml                  # Local configuration
`-- requirements.txt            # Python dependencies
```

## Installation

The setup script installs dependencies, registers the global `nxctl` command, and configures bash completion.

```bash
git clone https://github.com/nxctf/nxctl
cd nxctl

sudo ./setup.sh install
sudo ./setup.sh enable-service

source ~/.bashrc
```

## TTL and Extension System

NXCTL includes a safety mechanism to prevent challenges from running indefinitely:

1. Challenges automatically expire after the configured default TTL.
2. Expired challenges have both their container and active tunnel stopped.
3. Running challenges can be extended only inside the configured extension window.

```bash
nxctl extend web/sqli
```

## Automatic Exports

`nxctl up <challenge>` keeps the simple one-command flow and automatically creates every available export:

- `base_ip` direct URL when `base_ip` is configured.
- Ngrok tunnel for HTTP challenges when an ngrok token is configured or `NGROK_AUTHTOKEN` exists.
- The default protocol-based tunnel as before: Localtunnel for HTTP, Pinggy for TCP.

If one export fails, NXCTL keeps the challenge running and continues with the others. When no optional export is available, the default tunnel behavior remains the same as previous releases.

Example response shape from the API:

```json
{
  "challenge": "web/sqli",
  "status": "running",
  "port": 30001,
  "exports": [
    {
      "type": "direct",
      "provider": "base_ip",
      "url": "http://203.0.113.10:30001",
      "status": "running"
    },
    {
      "type": "tunnel",
      "provider": "ngrok",
      "url": "https://example.ngrok-free.app",
      "status": "running"
    },
    {
      "type": "tunnel",
      "provider": "localtunnel",
      "url": "https://example.loca.lt",
      "status": "running"
    }
  ]
}
```

## Command Reference

### Monitoring

| Command | Description | Example |
| --- | --- | --- |
| `nxctl list` | List all available challenges | `nxctl list` |
| `nxctl status` | Show running challenges, endpoints, and TTL | `nxctl status` |
| `nxctl inspect` | Show detailed challenge configuration | `nxctl inspect web/sqli` |
| `nxctl exports` | List all active tunnel exports | `nxctl exports` |

### Lifecycle

| Command | Description | Example |
| --- | --- | --- |
| `nxctl up` | Build, start, and auto-export a challenge | `nxctl up web/sqli` |
| `nxctl down` | Stop container and active tunnels | `nxctl down web/sqli` |
| `nxctl down --all` | Stop all running challenges and tunnel processes | `nxctl down --all` |
| `nxctl restart` | Restart a challenge | `nxctl restart web/sqli` |
| `nxctl extend` | Add time to a running challenge | `nxctl extend web/sqli` |

### Tunnels

| Command | Description | Example |
| --- | --- | --- |
| `nxctl export` | Manually start a tunnel | `nxctl export ngrok web/sqli` |
| `nxctl unexport` | Stop tunnels for a challenge | `nxctl unexport web/sqli` |

### Web API

| Command | Description | Example |
| --- | --- | --- |
| `nxctl api` | Run the FastAPI web server | `nxctl api --port 8000` |

The API is secured with the `X-NXCTL-Token` header. Set the token with `NXCTL_API_TOKEN`.

| Endpoint | Method | Description |
| --- | --- | --- |
| `/status` | GET | Comprehensive status of all challenges |
| `/up/{name}` | POST | Start a challenge |
| `/down/{name}` | POST | Stop a challenge |
| `/restart/{name}` | POST | Restart a challenge, with optional scope |
| `/extend/{name}` | POST | Add more time to a running challenge |

## Configuration

Key settings in `config.yml`:

```yaml
github_repo: https://github.com/nxctf/nxctl-challenges
branch: main
access_token: ${GITHUB_TOKEN}

db_file: ./data/nxctl.db
base_ip: "203.0.113.10"
enable_ngrok: true
enable_localtunnel: true
enable_pinggy: true

default_ttl_minutes: 15
extend_time_minutes: 10
extend_threshold_minutes: 5
extend_cooldown_seconds: 30
daemon_interval: 10
auto_heal_exports: true
```

Ngrok tokens can be provided with `ngrok_tokens` in `config.yml`, with `NGROK_AUTHTOKEN`, or through an existing ngrok config file.
When multiple HTTP challenges run at the same time, NXCTL uses a separate ngrok local API port per export and avoids reusing tokens that are already attached to active ngrok exports. If no unused token is available, the ngrok export fails cleanly while other exports continue.

## Quick Examples

```bash
nxctl sync
nxctl up web/sqli
nxctl status --watch
nxctl extend web/sqli
nxctl export pinggy web/sqli
nxctl down web/sqli
```

## Uninstall

```bash
sudo ./setup.sh uninstall
```

---

<div align="center">

**Built by the NXCTF community for the global cybersecurity ecosystem.**

</div>
