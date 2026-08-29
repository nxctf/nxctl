#!/usr/bin/env bash
set -euo pipefail

# System installer for NXCTL command wrappers and helper tooling.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
NXCTL_BIN_TARGET="/usr/local/bin/nxctl"
NXSCRIPT_BIN_TARGET="/usr/local/bin/nxscript"
PYTHON_MODE="auto"
VENV_DIR="${NXCTL_VENV_DIR:-${VIRTUAL_ENV:-$PROJECT_DIR/data/runtime/venv}}"
NXCTL_PYTHON_BIN=""

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
  --python-mode <auto|venv|system|system-break>
  --venv-dir <path>
  -h, --help
EOF
}

parse_install_options() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --python-mode)
                [[ $# -ge 2 ]] || die "--python-mode requires a value"
                PYTHON_MODE="$2"
                shift 2
                ;;
            --python-mode=*)
                PYTHON_MODE="${1#*=}"
                shift
                ;;
            --venv-dir)
                [[ $# -ge 2 ]] || die "--venv-dir requires a path"
                VENV_DIR="$2"
                shift 2
                ;;
            --venv-dir=*)
                VENV_DIR="${1#*=}"
                shift
                ;;
            *)
                die "Unknown install option: $1"
                ;;
        esac
    done

    case "$PYTHON_MODE" in
        auto|venv|system|system-break) ;;
        *) die "Invalid --python-mode: $PYTHON_MODE" ;;
    esac
}

python_is_externally_managed() {
    python3 - <<'PY'
from pathlib import Path
import sysconfig

marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
raise SystemExit(0 if marker.exists() else 1)
PY
}

ensure_system_pip() {
    if python3 -m pip --version >/dev/null 2>&1; then
        return 0
    fi
    warn "Python pip module is not installed."
    if confirm "Install python3-pip now?"; then
        run --label "Refreshing apt cache" sudo apt update
        run --label "Installing python3-pip" sudo apt install -y python3-pip
        return 0
    fi
    return 1
}

prepare_venv() {
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        NXCTL_PYTHON_BIN="$(cd "$(dirname "$VENV_DIR/bin/python")" && pwd)/python"
        return 0
    fi

    if ! python3 -m venv --help >/dev/null 2>&1; then
        warn "Python venv support is not installed."
        if confirm "Install python3-venv now?"; then
            run --label "Refreshing apt cache" sudo apt update
            run --label "Installing python3-venv" sudo apt install -y python3-venv
        else
            return 1
        fi
    fi

    mkdir -p "$(dirname "$VENV_DIR")"
    if ! run --label "Creating NXCTL virtual environment" python3 -m venv "$VENV_DIR"; then
        return 1
    fi
    [[ -x "$VENV_DIR/bin/python" ]] || return 1
    NXCTL_PYTHON_BIN="$(cd "$(dirname "$VENV_DIR/bin/python")" && pwd)/python"
}

install_requirements_with_python() {
    local python_bin="$1"
    run --label "Upgrading virtualenv pip" "$python_bin" -m pip install --upgrade pip || \
        warn "Could not upgrade virtualenv pip; continuing with the bundled version."
    if [[ -f "$REQUIREMENTS" ]]; then
        run --label "Installing Python requirements" "$python_bin" -m pip install -r "$REQUIREMENTS"
    fi
}

install_requirements_system() {
    local break_system="${1:-0}"
    ensure_system_pip || die "python3-pip is required for system installation"
    NXCTL_PYTHON_BIN="$(command -v python3)"
    [[ -f "$REQUIREMENTS" ]] || return 0

    if [[ "$break_system" -eq 1 ]]; then
        warn "Installing into externally-managed system Python by explicit request."
        run --label "Installing Python requirements (system break)" \
            sudo "$NXCTL_PYTHON_BIN" -m pip install --break-system-packages -r "$REQUIREMENTS"
    else
        if python_is_externally_managed; then
            die "System Python is externally managed. Use --python-mode venv or explicitly choose system-break."
        fi
        run --label "Installing Python requirements (system)" \
            sudo "$NXCTL_PYTHON_BIN" -m pip install -r "$REQUIREMENTS"
    fi
}

try_requirements_system_normal() {
    ensure_system_pip || return 1
    NXCTL_PYTHON_BIN="$(command -v python3)"
    [[ -f "$REQUIREMENTS" ]] || return 0

    if python_is_externally_managed; then
        warn "System Python is externally managed (PEP 668); normal pip installation is unavailable."
        return 1
    fi
    if ! run --label "Installing Python requirements (system)" \
        sudo "$NXCTL_PYTHON_BIN" -m pip install -r "$REQUIREMENTS"; then
        return 1
    fi
}

install_python_requirements() {
    case "$PYTHON_MODE" in
        venv)
            prepare_venv || die "Could not create the NXCTL virtual environment at $VENV_DIR"
            install_requirements_with_python "$NXCTL_PYTHON_BIN"
            ;;
        system)
            install_requirements_system 0
            ;;
        system-break)
            install_requirements_system 1
            ;;
        auto)
            if try_requirements_system_normal; then
                ok "Installed requirements with system Python."
            elif [[ ! -t 0 ]] || confirm "System Python installation is unavailable or failed. Install into an NXCTL virtual environment?"; then
                prepare_venv || die "Could not create the NXCTL virtual environment at $VENV_DIR"
                install_requirements_with_python "$NXCTL_PYTHON_BIN"
            else
                die "Python requirements were not installed. Retry with --python-mode venv or explicitly choose system-break."
            fi
            ;;
    esac

    run --label "Verifying Python requirements" "$NXCTL_PYTHON_BIN" -c \
        "import fastapi, uvicorn, psutil, yaml, pydantic, dotenv, pyngrok"
    ok "Python runtime: $NXCTL_PYTHON_BIN"
}

pinggy_is_healthy() {
    command -v pinggy >/dev/null 2>&1 && timeout 5 pinggy --version >/dev/null 2>&1
}

install_pinggy() {
    if pinggy_is_healthy; then
        ok "Pinggy is already installed and responding."
        return 0
    fi
    if command -v pinggy >/dev/null 2>&1; then
        warn "Pinggy was found but did not pass its version check."
    else
        info "Pinggy is not installed."
    fi
    if ! confirm "Install optional Pinggy tunnel provider?"; then
        info "Skipping optional Pinggy provider."
        return 0
    fi

    case "$(uname -m)" in
        x86_64|amd64) ;;
        *) die "Automatic Pinggy installation currently supports x86_64 only" ;;
    esac

    local temp_binary
    temp_binary="$(mktemp)"
    if ! run --label "Downloading pinggy" \
        wget -q "https://github.com/Pinggy-io/cli-js/releases/download/v0.4.7/pinggy-linux-x64" -O "$temp_binary"; then
        rm -f "$temp_binary"
        die "Failed to download Pinggy; any existing binary was left untouched"
    fi
    chmod 0755 "$temp_binary"
    run --label "Installing pinggy" sudo install -m 0755 "$temp_binary" /usr/local/bin/pinggy
    rm -f "$temp_binary"
    pinggy_is_healthy || die "Pinggy was installed but failed its version check"
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
    if [[ "${EUID:-$(id -u)}" -eq 0 && -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
        die "Run ./setup.sh install as your normal user, without sudo. The installer requests sudo only when needed."
    fi
    check_dependencies

    info "Preparing Python runtime ($PYTHON_MODE)..."
    install_python_requirements

    info "Installing tunneling tools..."

    if command -v npm >/dev/null 2>&1; then
        if ! command -v lt >/dev/null 2>&1; then
            run --label "Installing localtunnel" sudo npm install -g localtunnel || true
        fi
    fi

    install_pinggy

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
    local python_command
    printf -v python_command '%q' "$NXCTL_PYTHON_BIN"
    sudo tee "$NXCTL_BIN_TARGET" > /dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="\${PYTHONPATH:+\$PYTHONPATH:}$PROJECT_DIR/src"
export NXCTL_PYTHON=$python_command
exec $python_command -m nxctl.app "\$@"
EOF
    sudo chmod +x "$NXCTL_BIN_TARGET"
    ok "Created $NXCTL_BIN_TARGET"

    info "Installing nxscript command..."
    sudo tee "$NXSCRIPT_BIN_TARGET" > /dev/null <<EOF
#!/usr/bin/env bash
export NXCTL_PYTHON=$python_command
exec bash "$PROJECT_DIR/scripts/nxscript" "\$@"
EOF
    sudo chmod +x "$NXSCRIPT_BIN_TARGET"
    ok "Created $NXSCRIPT_BIN_TARGET"

    info "Installing bash completion..."
    bash "$PROJECT_DIR/scripts/completion/install.sh"

    if [ ! -f "$PROJECT_DIR/config.yml" ] && [ -f "$PROJECT_DIR/config.example.yml" ]; then
        cp "$PROJECT_DIR/config.example.yml" "$PROJECT_DIR/config.yml"
        warn "Created default config.yml from config.example.yml."
    fi

    if [ ! -f "$PROJECT_DIR/.env" ] && [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        warn "Created default .env from .env.example."
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

parse_install_options "$@"

install_nxctl "$@"
