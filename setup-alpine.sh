#!/usr/bin/env bash
set -e

# setup-alpine.sh - Interactive setup for CTF Orchestration Engine (ctfc) for Alpine Linux
# Modeled after setup.sh but adapted for apk and OpenRC

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETION_SRC="$PROJECT_DIR/src/completion/ctfs-back-completion.bash"
BIN_TARGET="/usr/local/bin/ctfc"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
INITD_SOURCE="$PROJECT_DIR/ctfc-daemon.initd"
INITD_TARGET="/etc/init.d/ctfc-daemon"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

check_dependencies() {
    echo -e "${GREEN}[*] Checking dependencies (Alpine)...${NC}"

    # Python3 & Pip
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ Python3 not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) apk update && apk add python3 py3-pip python3-dev build-base musl-dev libffi-dev ;;
            *) echo "❌ Failed: Python3 is required."; exit 1 ;;
        esac
    fi

    # Node.js (for localtunnel)
    if ! command -v npm >/dev/null 2>&1; then
        echo -e "${YELLOW}[!] npm not found. Required for localtunnel.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) apk update && apk add nodejs npm ;;
            *) echo "⚠️ Skipping npm/localtunnel." ;;
        esac
    fi

    # Docker
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*)
                apk update && apk add docker
                rc-update add docker default
                service docker start
                addgroup $USER docker
                echo -e "${YELLOW}[!] Added $USER to docker group. Restart may be needed.${NC}"
                ;;
            *) echo "❌ Failed: Docker is required."; exit 1 ;;
        esac
    fi

    # Docker Compose
    if ! docker compose version >/dev/null 2>&1; then
        echo -e "${YELLOW}[!] Docker Compose plugin not found.${NC}"
        read -p "👉 Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) apk update && apk add docker-cli-compose ;;
            *) echo "❌ Failed: Docker Compose is required."; exit 1 ;;
        esac
    fi

    # Utilities
    if ! command -v wget >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
        apk add wget curl
    fi
}

install_ctfc() {
    check_dependencies

    # Install Python Requirements (System Wide)
    if [ -f "$REQUIREMENTS" ]; then
        echo -e "${GREEN}[*] Installing Python requirements (System)...${NC}"
        # Alpine's pip also requires --break-system-packages for global install
        pip3 install --upgrade pip || true
        pip3 install -r "$REQUIREMENTS" --break-system-packages || pip3 install -r "$REQUIREMENTS"
    fi

    # Install External Tools
    echo -e "${GREEN}[*] Installing tunneling tools...${NC}"

    # Localtunnel
    if command -v npm >/dev/null 2>&1; then
        if ! command -v lt >/dev/null 2>&1; then
            npm install -g localtunnel || true
        fi
    fi

    # Pinggy
    if ! command -v pinggy >/dev/null 2>&1; then
        echo -e "${GREEN}[*] Downloading Pinggy binary...${NC}"
        wget -q "https://github.com/Pinggy-io/cli-js/releases/download/v0.4.7/pinggy-linux-x64" -O /usr/local/bin/pinggy
        chmod +x /usr/local/bin/pinggy
    fi

    # Create Data Directories
    mkdir -p "$PROJECT_DIR/data/chall" "$PROJECT_DIR/data/build" "$PROJECT_DIR/data/logs"

    # Create Binary Symlink
    echo -e "${GREEN}[*] Installing ctfc command...${NC}"

    # Alpine uses /bin/bash if installed, otherwise /bin/sh
    SHELL_BIN="/bin/sh"
    if [ -f "/bin/bash" ]; then SHELL_BIN="/bin/bash"; fi

    WRAPPER="#!$SHELL_BIN
export PYTHONPATH=\$PYTHONPATH:$PROJECT_DIR
python3 $PROJECT_DIR/src/app.py \"\$@\"
"
    echo "$WRAPPER" > "$BIN_TARGET"
    chmod +x "$BIN_TARGET"
    echo -e "  -> Created $BIN_TARGET"

    # Install Bash Completion (if bash exists)
    if [ -f "/bin/bash" ] && [ -f "$COMPLETION_SRC" ]; then
        echo -e "${GREEN}[*] Installing bash completion...${NC}"
        sed -i 's/\r$//' "$COMPLETION_SRC" 2>/dev/null || true

        # Check for .bashrc or .profile
        BASH_CONFIG="$HOME/.bashrc"
        if [ ! -f "$BASH_CONFIG" ]; then BASH_CONFIG="$HOME/.profile"; fi

        if ! grep -q "source $COMPLETION_SRC" "$BASH_CONFIG"; then
            echo -e "\n# CTF Container Completion" >> "$BASH_CONFIG"
            echo "source $COMPLETION_SRC" >> "$BASH_CONFIG"
            echo -e "  -> Added to $BASH_CONFIG"
        fi
    fi

    # Config Check
    if [ ! -f "$PROJECT_DIR/config.yml" ]; then
        if [ -f "$PROJECT_DIR/config.example.yml" ]; then
            cp "$PROJECT_DIR/config.example.yml" "$PROJECT_DIR/config.yml"
            echo -e "${YELLOW}[!] Created default config.yml from template.${NC}"
        fi
    fi

    echo -e "\n${GREEN}✅ ctfc installed successfully on Alpine!${NC}"
    echo -e "Try it with: ${YELLOW}ctfc status${NC}\n"
}

uninstall_ctfc() {
    echo -e "${YELLOW}[*] Uninstalling ctfc...${NC}"

    if [ -f "$BIN_TARGET" ]; then
        rm -f "$BIN_TARGET"
        echo "  -> Removed $BIN_TARGET"
    fi

    # Clean up completion
    if [ -f "$HOME/.bashrc" ]; then
        sed -i "\|source $COMPLETION_SRC|d" "$HOME/.bashrc"
    fi
    if [ -f "$HOME/.profile" ]; then
        sed -i "\|source $COMPLETION_SRC|d" "$HOME/.profile"
    fi

    echo -e "${GREEN}✅ ctfc uninstalled.${NC}\n"
}

enable_service() {
    echo -e "${YELLOW}[*] Enabling ctfc-daemon OpenRC service...${NC}"

    if [ ! -f "$INITD_SOURCE" ]; then
        echo -e "${RED}❌ Error: $INITD_SOURCE not found.${NC}"
        exit 1
    fi

    # Create directory variable for the script
    sed "s|directory=\"/opt/ctfs-back\"|directory=\"$PROJECT_DIR\"|" "$INITD_SOURCE" > "$INITD_TARGET"

    # Set execution permissions
    chmod +x "$INITD_TARGET"

    # Add to default runlevel and start
    rc-update add ctfc-daemon default
    service ctfc-daemon restart

    echo -e "${GREEN}✅ Service enabled and started via OpenRC!${NC}"
    echo -e "Check status with: ${YELLOW}service ctfc-daemon status${NC}\n"
}

disable_service() {
    echo -e "${YELLOW}[*] Disabling ctfc-daemon OpenRC service...${NC}"
    service ctfc-daemon stop
    rc-update del ctfc-daemon default
    rm -f "$INITD_TARGET"
    echo -e "${GREEN}✅ Service disabled and removed.${NC}\n"
}

case "$1" in
    install)
        install_ctfc
        ;;
    uninstall)
        uninstall_ctfc
        ;;
    enable-service)
        enable_service
        ;;
    disable-service)
        disable_service
        ;;
    *)
        echo "Usage: $0 [install|uninstall|enable-service|disable-service]"
        ;;
esac
