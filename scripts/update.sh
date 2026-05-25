#!/usr/bin/env bash
set -euo pipefail

# Refresh installed NXCTL wrappers after the repository has been updated.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="nxctl-daemon"
WAS_ACTIVE=0
WAS_ENABLED=0
HAD_SERVICE=0

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/log.sh
source "$PROJECT_DIR/scripts/lib/log.sh"

usage() {
    cat <<'EOF'
Usage: nxscript [common flags] update

Common flags:
  -v, --verbose
  --no-spinner
  -h, --help
EOF
}

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
    usage
    exit 0
fi

if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        WAS_ACTIVE=1
        HAD_SERVICE=1
    fi
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        WAS_ENABLED=1
        HAD_SERVICE=1
    fi
    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        HAD_SERVICE=1
    fi
fi

if [ "$HAD_SERVICE" -eq 1 ]; then
    info "Disabling existing $SERVICE_NAME service before update..."
    bash "$PROJECT_DIR/scripts/service.sh" uninstall
fi

info "Removing installed command wrappers..."
bash "$PROJECT_DIR/scripts/uninstall.sh"

info "Installing updated command wrappers..."
bash "$PROJECT_DIR/scripts/install.sh"

if [ "$WAS_ENABLED" -eq 1 ] || [ "$WAS_ACTIVE" -eq 1 ]; then
    info "Restoring $SERVICE_NAME service..."
    bash "$PROJECT_DIR/scripts/service.sh" install
    if [ "$WAS_ACTIVE" -eq 1 ]; then
        sudo systemctl restart "$SERVICE_NAME"
    fi
fi

ok "NXCTL update complete."
