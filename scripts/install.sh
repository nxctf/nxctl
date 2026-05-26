#!/usr/bin/env bash
set -euo pipefail

# System installer for NXCTL command wrappers and helper tooling.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
NXCTL_BIN_TARGET="/usr/local/bin/nxctl"
NXSCRIPT_BIN_TARGET="/usr/local/bin/nxscript"

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"
# shellcheck source=lib/prompt.sh
source "$PROJECT_DIR/scripts/lib/prompt.sh"

usage() {
    cat <<'EOF'
Usage: scripts/install.sh [common flags]

Common flags:
  -v, --verbose
  --no-spinner
  -h, --help
EOF
}

check_dependencies() {
    info "Checking dependencies..."

    if ! command -v python3 >/dev/null 2>&1; then
        err "Python3 not found."
        if confirm "Do you want to install it now?"; then
            run --label "Installing Python3" sudo apt update
            run --label "Installing python3/python3-pip" sudo apt install -y python3 python3-pip
        else
            die "Python3 is required."
        fi
    fi

    if ! command -v pip3 >/dev/null 2>&1; then
        err "pip3 not found."
        if confirm "Do you want to install it now?"; then
            run --label "Installing pip3" sudo apt update
            run --label "Installing python3-pip" sudo apt install -y python3-pip
        else
            die "pip3 is required."
        fi
    fi

    if ! command -v npm >/dev/null 2>&1; then
        warn "npm not found. Required for localtunnel."
        if confirm "Do you want to install it now?"; then
            run --label "Installing npm" sudo apt update
            run --label "Installing npm package" sudo apt install -y npm
        else
            warn "Skipping npm/localtunnel."
        fi
    fi

    if ! command -v docker >/dev/null 2>&1; then
        err "Docker not found."
        if confirm "Do you want to install it now?"; then
            run --label "Downloading Docker installer" curl -fsSL https://get.docker.com -o get-docker.sh
            run --label "Installing Docker" sudo sh get-docker.sh
            run --label "Adding $USER to docker group" sudo usermod -aG docker "$USER"
            warn "Added $USER to docker group. Restart may be needed."
            rm get-docker.sh
        else
            die "Docker is required."
        fi
    fi

    if ! docker compose version >/dev/null 2>&1; then
        HAS_LEGACY=false
        if command -v docker-compose >/dev/null 2>&1; then
            HAS_LEGACY=true
            warn "Found legacy 'docker-compose' but 'docker compose' is missing."
            compose_prompt="Do you want to install the modern Docker Compose plugin?"
        else
            warn "Docker Compose not found."
            compose_prompt="Do you want to install it now?"
        fi

        if confirm "$compose_prompt"; then
            info "Adding Docker repository and installing plugin..."
            run --label "Refreshing apt cache" sudo apt-get update
            run --label "Installing Docker apt dependencies" sudo apt-get install -y ca-certificates curl gnupg
            run --label "Creating apt keyring directory" sudo install -m 0755 -d /etc/apt/keyrings
            run --label "Installing Docker GPG key" bash -c 'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes'
            run --label "Setting Docker GPG permissions" sudo chmod a+r /etc/apt/keyrings/docker.gpg

            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

            run --label "Refreshing apt cache" sudo apt-get update
            run --label "Installing Docker Compose plugin" sudo apt-get install -y docker-compose-plugin
        elif [ "$HAS_LEGACY" = false ]; then
            die "Docker Compose is required."
        else
            warn "Proceeding with legacy 'docker-compose' as fallback."
        fi
    fi
}

install_nxctl() {
    check_dependencies

    if [ -f "$REQUIREMENTS" ]; then
        info "Installing Python requirements (system-wide)..."
        run --label "Upgrading pip" sudo pip3 install --upgrade pip || true
        run --label "Installing Python requirements" sudo pip3 install -r "$REQUIREMENTS" --break-system-packages || run --label "Installing Python requirements" sudo pip3 install -r "$REQUIREMENTS"
    fi

    info "Installing tunneling tools..."

    if command -v npm >/dev/null 2>&1; then
        if ! command -v lt >/dev/null 2>&1; then
            run --label "Installing localtunnel" sudo npm install -g localtunnel || true
        fi
    fi

    if ! command -v pinggy >/dev/null 2>&1; then
        info "Downloading Pinggy binary..."
        run --label "Downloading pinggy" sudo wget -q "https://github.com/Pinggy-io/cli-js/releases/download/v0.4.7/pinggy-linux-x64" -O /usr/local/bin/pinggy
        run --label "Making pinggy executable" sudo chmod +x /usr/local/bin/pinggy
    fi

    if ! command -v cloudflared >/dev/null 2>&1; then
        info "Downloading Cloudflared binary..."
        run --label "Downloading cloudflared" sudo wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -O /usr/local/bin/cloudflared
        run --label "Making cloudflared executable" sudo chmod +x /usr/local/bin/cloudflared
    fi

    if ! command -v bore >/dev/null 2>&1; then
        info "Downloading Bore binary..."
        run --label "Downloading bore" sudo wget -q "https://github.com/ekzhang/bore/releases/download/v0.6.0/bore-v0.6.0-x86_64-unknown-linux-musl.tar.gz" -O /tmp/bore.tar.gz
        run --label "Extracting bore" sudo tar -xzf /tmp/bore.tar.gz -C /tmp
        run --label "Making bore executable" sudo chmod +x /tmp/bore
        run --label "Installing bore" sudo mv /tmp/bore /usr/local/bin/
        sudo rm -f /tmp/bore.tar.gz
    fi

    mkdir -p "$PROJECT_DIR/data"

    info "Installing nxctl command..."
    sudo tee "$NXCTL_BIN_TARGET" > /dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="\${PYTHONPATH:+\$PYTHONPATH:}$PROJECT_DIR/src"
exec python3 -m nxctl.app "\$@"
EOF
    sudo chmod +x "$NXCTL_BIN_TARGET"
    ok "Created $NXCTL_BIN_TARGET"

    info "Installing nxscript command..."
    sudo tee "$NXSCRIPT_BIN_TARGET" > /dev/null <<EOF
#!/usr/bin/env bash
exec "$PROJECT_DIR/scripts/nxscript" "\$@"
EOF
    sudo chmod +x "$NXSCRIPT_BIN_TARGET"
    chmod +x "$PROJECT_DIR/scripts/nxscript"
    ok "Created $NXSCRIPT_BIN_TARGET"

    info "Installing bash completion..."
    bash "$PROJECT_DIR/scripts/completion/install.sh"

    if [ ! -f "$PROJECT_DIR/config.yml" ]; then
        if [ -f "$PROJECT_DIR/config.example.yml" ]; then
            cp "$PROJECT_DIR/config.example.yml" "$PROJECT_DIR/config.yml"
            warn "Created default config.yml from template."
        fi
    fi

    info "Installing/updating daemon service..."
    bash "$PROJECT_DIR/scripts/service.sh" install-start

    echo
    ok "NXCTL installed successfully (system-wide)."
    echo "Restart your shell or run: ${YELLOW}source ~/.bashrc${RST}"
    echo "Try it with: ${YELLOW}nxctl status${RST}"
    echo "Update later with: ${YELLOW}nxscript update${RST}"
    echo "Helper command: ${YELLOW}nxscript --help${RST}"
    echo
}

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
    usage
    exit 0
fi

install_nxctl "$@"
