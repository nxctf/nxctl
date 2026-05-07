#!/usr/bin/env bash
set -euo pipefail

# setup.sh - install system tools and Python deps for CTF Orchestrator
# Runs on Debian/Ubuntu. For other OS adapt package manager commands.

echo "[setup] Starting setup..."

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip curl unzip gnupg ca-certificates npm
  # docker
  if ! command -v docker >/dev/null 2>&1; then
    echo "[setup] Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    sudo usermod -aG docker "$USER" || true
  fi
  # docker compose plugin is usually provided as docker compose
  if ! docker compose version >/dev/null 2>&1; then
    echo "[setup] Docker Compose plugin not found; attempting to install python docker-compose as fallback"
    sudo apt-get install -y docker-compose
  fi
fi

# echo "[setup] Creating Python venv..."
# python3 -m venv .venv
# source .venv/bin/activate

echo "[setup] Upgrading pip and installing Python requirements..."
pip install --upgrade pip
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

echo "[setup] Installing pyngrok for ngrok programmatic control..."
pip install pyngrok

echo "[setup] Installing localtunnel (optional) via npm if available..."
if command -v npm >/dev/null 2>&1; then
  sudo npm install -g localtunnel || true
else
  echo "[setup] npm not found — skip localtunnel install"
fi

echo "[setup] Done. Note: for ngrok you should set NGROK authtoken via 'ngrok authtoken <token>' or set in config.yml"
echo "Activate virtualenv with: source .venv/bin/activate"

exit 0

wget https://github.com/Pinggy-io/cli-js/releases/download/v0.4.7/pinggy-linux-x64 -o pinggy
chmod +x pinggy
sudo mv pinggy /usr/bin/pinggy
