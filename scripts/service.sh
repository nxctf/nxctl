#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="nxctl-daemon"
SERVICE_SRC="$PROJECT_DIR/scripts/service/$SERVICE_NAME.service"
SERVICE_DST="/etc/systemd/system/$SERVICE_NAME.service"

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"

install_service() {
    if [ ! -f "$SERVICE_SRC" ]; then
        die "Service template not found: $SERVICE_SRC"
    fi

    local current_user
    local temp_service
    current_user="$(whoami)"
    temp_service="$(mktemp)"

    cp "$SERVICE_SRC" "$temp_service"
    sed -i "s/User=root/User=$current_user/" "$temp_service"
    if ! grep -q '^WorkingDirectory=' "$temp_service"; then
        sed -i "/User=$current_user/a WorkingDirectory=$PROJECT_DIR" "$temp_service"
    fi

    info "Installing $SERVICE_NAME systemd service..."
    echo "  -> User: $current_user"
    echo "  -> WorkingDirectory: $PROJECT_DIR"

    run --label "Writing systemd service" sudo cp "$temp_service" "$SERVICE_DST"
    rm -f "$temp_service"
    run --label "Reloading systemd" sudo systemctl daemon-reload
    run --label "Enabling $SERVICE_NAME" sudo systemctl enable "$SERVICE_NAME"
}

ensure_service_installed() {
    if [ ! -f "$SERVICE_DST" ]; then
        install_service
    fi
}

uninstall_service() {
    info "Removing $SERVICE_NAME systemd service..."
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    run --label "Removing systemd service" sudo rm -f "$SERVICE_DST"
    run --label "Reloading systemd" sudo systemctl daemon-reload
    ok "Service removed."
}

usage() {
    echo "Usage: nxscript [common flags] service start|stop|restart|status"
    echo "       nxscript [common flags] service install|uninstall"
}

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

COMMAND="${1:-status}"
if [[ $# -gt 0 ]]; then
    shift
fi

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
    usage
    exit 0
fi

case "$COMMAND" in
    install)
        install_service
        ;;
    install-start)
        install_service
        sudo systemctl restart "$SERVICE_NAME"
        ;;
    uninstall|remove|disable)
        uninstall_service
        ;;
    start)
        ensure_service_installed
        sudo systemctl start "$SERVICE_NAME"
        ;;
    stop)
        sudo systemctl stop "$SERVICE_NAME"
        ;;
    restart)
        ensure_service_installed
        sudo systemctl restart "$SERVICE_NAME"
        ;;
    status)
        if ! command -v systemctl >/dev/null 2>&1; then
            warn "systemctl not found; $SERVICE_NAME status is unavailable on this host."
            exit 0
        fi
        systemctl status "$SERVICE_NAME" || true
        ;;
    help)
        usage
        ;;
    *)
        echo "Unknown service command: $COMMAND" >&2
        echo "Usage: nxscript service start|stop|restart|status" >&2
        exit 1
        ;;
esac
