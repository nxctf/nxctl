#!/usr/bin/env bash
set -e

# setup.sh - Interactive setup for CTF Orchestration Engine (ctfc)
# Modeled after HPone setup style - NO VENV MODE

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETION_SRC="$PROJECT_DIR/src/completion/ctfs-back-completion.bash"
BIN_TARGET="/usr/local/bin/ctfc"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

check_dependencies() {
    echo -e "${GREEN}[*] Checking dependencies...${NC}"

    # Python3
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ Python3 not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y python3 python3-pip ;;
            *) echo "❌ Failed: Python3 is required."; exit 1 ;;
        esac
    fi

    # Pip3
    if ! command -v pip3 >/dev/null 2>&1; then
        echo -e "${RED}❌ pip3 not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y python3-pip ;;
            *) echo "❌ Failed: pip3 is required."; exit 1 ;;
        esac
    fi

    # Node.js (for localtunnel)
    if ! command -v npm >/dev/null 2>&1; then
        echo -e "${YELLOW}[!] npm not found. Required for localtunnel.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y npm ;;
            *) echo "⚠️ Skipping npm/localtunnel." ;;
        esac
    fi

    # Docker
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*)
                curl -fsSL https://get.docker.com -o get-docker.sh
                sudo sh get-docker.sh
                sudo usermod -aG docker "$USER"
                echo -e "${YELLOW}[!] Added $USER to docker group. Restart may be needed.${NC}"
                rm get-docker.sh
                ;;
            *) echo "❌ Failed: Docker is required."; exit 1 ;;
        esac
    fi

    # Docker Compose
    if ! docker compose version >/dev/null 2>&1; then
        echo -e "${YELLOW}[!] Docker Compose plugin not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y docker-compose-plugin ;;
            *) echo "❌ Failed: Docker Compose is required."; exit 1 ;;
        esac
    fi
}

install_ctfc() {
    check_dependencies

    # Install Python Requirements (System Wide)
    if [ -f "$REQUIREMENTS" ]; then
        echo -e "${GREEN}[*] Installing Python requirements (System)...${NC}"
        # We use --break-system-packages for newer Debian/Ubuntu that block system-wide pip
        sudo pip3 install --upgrade pip || true
        sudo pip3 install -r "$REQUIREMENTS" --break-system-packages || sudo pip3 install -r "$REQUIREMENTS"
    fi

    # Install External Tools
    echo -e "${GREEN}[*] Installing tunneling tools...${NC}"

    # Localtunnel
    if command -v npm >/dev/null 2>&1; then
        if ! command -v lt >/dev/null 2>&1; then
            sudo npm install -g localtunnel || true
        fi
    fi

    # Pinggy
    if ! command -v pinggy >/dev/null 2>&1; then
        echo -e "${GREEN}[*] Downloading Pinggy binary...${NC}"
        sudo wget -q "https://github.com/Pinggy-io/cli-js/releases/download/v0.4.7/pinggy-linux-x64" -O /usr/local/bin/pinggy
        sudo chmod +x /usr/local/bin/pinggy
    fi

    # Create Data Directories
    mkdir -p "$PROJECT_DIR/data/chall" "$PROJECT_DIR/data/build" "$PROJECT_DIR/data/logs"

    # Create Binary Symlink
    echo -e "${GREEN}[*] Installing ctfc command...${NC}"

    # Simple wrapper without venv
    WRAPPER="#!/bin/bash
export PYTHONPATH=\$PYTHONPATH:$PROJECT_DIR
python3 $PROJECT_DIR/src/app.py \"\$@\"
"
    echo "$WRAPPER" | sudo tee "$BIN_TARGET" > /dev/null
    sudo chmod +x "$BIN_TARGET"
    echo -e "  -> Created $BIN_TARGET"

    # Install Bash Completion
    if [ -f "$COMPLETION_SRC" ]; then
        echo -e "${GREEN}[*] Installing bash completion...${NC}"
        # Ensure correct line endings
        sed -i 's/\r$//' "$COMPLETION_SRC" 2>/dev/null || true

        if ! grep -q "source $COMPLETION_SRC" "$HOME/.bashrc"; then
            echo -e "\n# CTF Container Completion" >> "$HOME/.bashrc"
            echo "source $COMPLETION_SRC" >> "$HOME/.bashrc"
            echo -e "  -> Added to ~/.bashrc"
        fi
    fi

    # Config Check
    if [ ! -f "$PROJECT_DIR/config.yml" ]; then
        if [ -f "$PROJECT_DIR/config.example.yml" ]; then
            cp "$PROJECT_DIR/config.example.yml" "$PROJECT_DIR/config.yml"
            echo -e "${YELLOW}[!] Created default config.yml from template.${NC}"
        fi
    fi

    echo -e "\n${GREEN}✅ ctfc installed successfully (System-wide)!${NC}"
    echo -e "Restart your shell or run: ${YELLOW}source ~/.bashrc${NC}"
    echo -e "Try it with: ${YELLOW}ctfc status${NC}\n"
}

uninstall_ctfc() {
    echo -e "${YELLOW}[*] Uninstalling ctfc...${NC}"

    if [ -f "$BIN_TARGET" ]; then
        sudo rm -f "$BIN_TARGET"
        echo "  -> Removed $BIN_TARGET"
    fi

    if grep -q "source $COMPLETION_SRC" "$HOME/.bashrc"; then
        sed -i "\|source $COMPLETION_SRC|d" "$HOME/.bashrc"
        echo "  -> Removed completion from ~/.bashrc"
    fi

    echo -e "${GREEN}✅ ctfc uninstalled.${NC}\n"
}

case "$1" in
    install)
        install_ctfc
        ;;
    uninstall)
        uninstall_ctfc
        ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        ;;
esac
