#!/usr/bin/env bash
set -euo pipefail

# Remove installed NXCTL wrappers and service unit. Runtime data is kept.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="nxctl-daemon"
HAD_SERVICE=0

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/log.sh
source "$PROJECT_DIR/scripts/lib/log.sh"

usage() {
    cat <<'EOF'
Usage: nxscript [common flags] delete

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
        HAD_SERVICE=1
    fi
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        HAD_SERVICE=1
    fi
    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        HAD_SERVICE=1
    fi
fi

if [ "$HAD_SERVICE" -eq 1 ]; then
    info "Removing $SERVICE_NAME service before delete..."
    bash "$PROJECT_DIR/scripts/service.sh" uninstall
fi

bash "$PROJECT_DIR/scripts/uninstall.sh"
