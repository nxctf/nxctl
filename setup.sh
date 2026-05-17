#!/usr/bin/env bash
set -e

# setup.sh - Interactive setup for NXCTL

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETION_SRC="$PROJECT_DIR/completion/nxctl-completion.bash"
NXCTL_BIN_TARGET="/usr/local/bin/nxctl"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_NAME="nxctl-daemon"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

check_dependencies() {
    echo -e "${GREEN}[*] Checking dependencies...${NC}"

    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}[x] Python3 not found.${NC}"
        read -p "Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y python3 python3-pip ;;
            *) echo "[x] Failed: Python3 is required."; exit 1 ;;
        esac
    fi

    if ! command -v pip3 >/dev/null 2>&1; then
        echo -e "${RED}[x] pip3 not found.${NC}"
        read -p "Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y python3-pip ;;
            *) echo "[x] Failed: pip3 is required."; exit 1 ;;
        esac
    fi

    if ! command -v npm >/dev/null 2>&1; then
        echo -e "${YELLOW}[!] npm not found. Required for localtunnel.${NC}"
        read -p "Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*) sudo apt update && sudo apt install -y npm ;;
            *) echo "[!] Skipping npm/localtunnel." ;;
        esac
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}[x] Docker not found.${NC}"
        read -p "Do you want to install it now? (y/n): " yn
        case $yn in
            [Yy]*)
                curl -fsSL https://get.docker.com -o get-docker.sh
                sudo sh get-docker.sh
                sudo usermod -aG docker "$USER"
                echo -e "${YELLOW}[!] Added $USER to docker group. Restart may be needed.${NC}"
                rm get-docker.sh
                ;;
            *) echo "[x] Failed: Docker is required."; exit 1 ;;
        esac
    fi

    if ! docker compose version >/dev/null 2>&1; then
        HAS_LEGACY=false
        if command -v docker-compose >/dev/null 2>&1; then
            HAS_LEGACY=true
            echo -e "${YELLOW}[!] Found legacy 'docker-compose' but 'docker compose' is missing.${NC}"
            read -p "Do you want to install the modern Docker Compose plugin? (y/n): " yn
        else
            echo -e "${YELLOW}[!] Docker Compose not found.${NC}"
            read -p "Do you want to install it now? (y/n): " yn
        fi

        case $yn in
            [Yy]*)
                echo -e "${GREEN}[*] Adding Docker repository and installing plugin...${NC}"
                sudo apt-get update
                sudo apt-get install -y ca-certificates curl gnupg
                sudo install -m 0755 -d /etc/apt/keyrings
                curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
                sudo chmod a+r /etc/apt/keyrings/docker.gpg

                echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
                sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

                sudo apt-get update
                sudo apt-get install -y docker-compose-plugin
                ;;
            *)
                if [ "$HAS_LEGACY" = false ]; then
                    echo -e "${RED}[x] Failed: Docker Compose is required.${NC}"
                    exit 1
                else
                    echo -e "${YELLOW}[!] Proceeding with legacy 'docker-compose' as fallback.${NC}"
                fi
                ;;
        esac
    fi
}

install_nxctl() {
    check_dependencies

    if [ -f "$REQUIREMENTS" ]; then
        echo -e "${GREEN}[*] Installing Python requirements (system-wide)...${NC}"
        sudo pip3 install --upgrade pip || true
        sudo pip3 install -r "$REQUIREMENTS" --break-system-packages || sudo pip3 install -r "$REQUIREMENTS"
    fi

    echo -e "${GREEN}[*] Installing tunneling tools...${NC}"

    if command -v npm >/dev/null 2>&1; then
        if ! command -v lt >/dev/null 2>&1; then
            sudo npm install -g localtunnel || true
        fi
    fi

    if ! command -v pinggy >/dev/null 2>&1; then
        echo -e "${GREEN}[*] Downloading Pinggy binary...${NC}"
        sudo wget -q "https://github.com/Pinggy-io/cli-js/releases/download/v0.4.7/pinggy-linux-x64" -O /usr/local/bin/pinggy
        sudo chmod +x /usr/local/bin/pinggy
    fi

    mkdir -p "$PROJECT_DIR/data/chall" "$PROJECT_DIR/data/build" "$PROJECT_DIR/data/logs"

    echo -e "${GREEN}[*] Installing nxctl command...${NC}"
    NXCTL_WRAPPER="#!/bin/bash
export PYTHONPATH=\$PYTHONPATH:$PROJECT_DIR/src
python3 -m nxctl.app \"\$@\"
"
    echo "$NXCTL_WRAPPER" | sudo tee "$NXCTL_BIN_TARGET" > /dev/null
    sudo chmod +x "$NXCTL_BIN_TARGET"
    echo -e "  -> Created $NXCTL_BIN_TARGET"

    if [ -f "$COMPLETION_SRC" ]; then
        echo -e "${GREEN}[*] Installing bash completion...${NC}"
        sed -i 's/\r$//' "$COMPLETION_SRC" 2>/dev/null || true
        sed -i "\|ctfs-back-completion.bash|d" "$HOME/.bashrc" 2>/dev/null || true

        if ! grep -q "source $COMPLETION_SRC" "$HOME/.bashrc"; then
            echo -e "\n# NXCTL completion" >> "$HOME/.bashrc"
            echo "source $COMPLETION_SRC" >> "$HOME/.bashrc"
            echo -e "  -> Added to ~/.bashrc"
        fi
    fi

    if [ ! -f "$PROJECT_DIR/config.yml" ]; then
        if [ -f "$PROJECT_DIR/config.example.yml" ]; then
            cp "$PROJECT_DIR/config.example.yml" "$PROJECT_DIR/config.yml"
            echo -e "${YELLOW}[!] Created default config.yml from template.${NC}"
        fi
    fi

    echo -e "\n${GREEN}[ok] NXCTL installed successfully (system-wide).${NC}"
    echo -e "Restart your shell or run: ${YELLOW}source ~/.bashrc${NC}"
    echo -e "Try it with: ${YELLOW}nxctl status${NC}\n"
}

uninstall_nxctl() {
    echo -e "${YELLOW}[*] Uninstalling NXCTL...${NC}"

    if [ -f "$NXCTL_BIN_TARGET" ]; then
        sudo rm -f "$NXCTL_BIN_TARGET"
        echo "  -> Removed $NXCTL_BIN_TARGET"
    fi

    if grep -q "source $COMPLETION_SRC" "$HOME/.bashrc"; then
        sed -i "\|source $COMPLETION_SRC|d" "$HOME/.bashrc"
        echo "  -> Removed completion from ~/.bashrc"
    fi

    echo -e "${GREEN}[ok] NXCTL uninstalled.${NC}\n"
}

enable_service() {
    echo -e "${YELLOW}[*] Enabling $SERVICE_NAME systemd service...${NC}"
    SERVICE_FILE="$SERVICE_NAME.service"
    CURRENT_USER=$(whoami)
    PROJECT_PATH=$(pwd)

    if [ ! -f "$SERVICE_FILE" ]; then
        echo -e "${RED}[x] Error: $SERVICE_FILE not found in current directory.${NC}"
        exit 1
    fi

    TEMP_SERVICE="/tmp/$SERVICE_FILE"
    cp "$SERVICE_FILE" "$TEMP_SERVICE"

    sed -i "s/User=root/User=$CURRENT_USER/" "$TEMP_SERVICE"
    sed -i "/User=$CURRENT_USER/a WorkingDirectory=$PROJECT_PATH" "$TEMP_SERVICE"

    echo "  -> Configuring service for user: $CURRENT_USER"
    echo "  -> Project path: $PROJECT_PATH"

    sudo cp "$TEMP_SERVICE" "$SYSTEMD_DIR/$SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"

    rm -f "$TEMP_SERVICE"

    echo -e "${GREEN}[ok] Service enabled and started as user $CURRENT_USER.${NC}"
    echo -e "Check status with: ${YELLOW}sudo systemctl status $SERVICE_NAME${NC}\n"
}

disable_service() {
    echo -e "${YELLOW}[*] Disabling $SERVICE_NAME systemd service...${NC}"
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    sudo rm -f "$SYSTEMD_DIR/$SERVICE_NAME.service"

    sudo systemctl daemon-reload
    echo -e "${GREEN}[ok] Service disabled and removed.${NC}\n"
}

case "$1" in
    install)
        install_nxctl
        ;;
    uninstall)
        uninstall_nxctl
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
