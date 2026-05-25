#!/usr/bin/env bash
# Uninstall script for NXCTL bash completion.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET_HOME="$HOME"

# shellcheck source=../lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=../lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"

usage() {
    cat <<'EOF'
Usage: scripts/completion/uninstall.sh [common flags]

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

if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
    sudo_home="$(getent passwd "$SUDO_USER" 2>/dev/null | cut -d: -f6 || true)"
    TARGET_HOME="${sudo_home:-$(eval echo "~$SUDO_USER")}"
fi

log_info "Uninstalling NXCTL bash completion..."

cleanup_bashrc_completion() {
    if [[ -f "${TARGET_HOME}/.bashrc" ]]; then
        tmp_file="$(mktemp)"
        (grep -v -E "nxctl-completion\\.bash|nxscript-completion\\.bash|ctfs-back-completion\\.bash" "${TARGET_HOME}/.bashrc" || true) > "${tmp_file}"
        mv "${tmp_file}" "${TARGET_HOME}/.bashrc"
        if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
            chown "$SUDO_USER" "${TARGET_HOME}/.bashrc" 2>/dev/null || true
        fi
        log_ok "Removed completion source lines from ${TARGET_HOME}/.bashrc"
    fi
}

if [[ -f "/etc/bash_completion.d/nxctl" ]]; then
    if [[ $EUID -eq 0 ]]; then
        run_cmd --label "Removing system nxctl completion" rm -f /etc/bash_completion.d/nxctl
    else
        run_cmd --label "Removing system nxctl completion" sudo rm -f /etc/bash_completion.d/nxctl
    fi
    log_ok "Removed system-wide nxctl completion"
fi

if [[ -f "/etc/bash_completion.d/nxscript" ]]; then
    if [[ $EUID -eq 0 ]]; then
        run_cmd --label "Removing system nxscript completion" rm -f /etc/bash_completion.d/nxscript
    else
        run_cmd --label "Removing system nxscript completion" sudo rm -f /etc/bash_completion.d/nxscript
    fi
    log_ok "Removed system-wide nxscript completion"
fi

if [[ -f "${TARGET_HOME}/.bash_completion.d/nxctl" ]]; then
    run_cmd --label "Removing user nxctl completion" rm -f "${TARGET_HOME}/.bash_completion.d/nxctl"
    log_ok "Removed user nxctl completion file"
fi

if [[ -f "${TARGET_HOME}/.bash_completion.d/nxscript" ]]; then
    run_cmd --label "Removing user nxscript completion" rm -f "${TARGET_HOME}/.bash_completion.d/nxscript"
    log_ok "Removed user nxscript completion file"
fi

cleanup_bashrc_completion

echo ""
log_ok "Uninstall complete."
