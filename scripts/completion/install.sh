#!/usr/bin/env bash
# Installation script for NXCTL bash completion.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
NXCTL_COMPLETION_SCRIPT="${SCRIPT_DIR}/nxctl-completion.bash"
NXSCRIPT_COMPLETION_SCRIPT="${SCRIPT_DIR}/nxscript-completion.bash"
ABS_NXCTL_COMPLETION_SCRIPT="$(cd "$(dirname "${NXCTL_COMPLETION_SCRIPT}")" && pwd)/$(basename "${NXCTL_COMPLETION_SCRIPT}")"
ABS_NXSCRIPT_COMPLETION_SCRIPT="$(cd "$(dirname "${NXSCRIPT_COMPLETION_SCRIPT}")" && pwd)/$(basename "${NXSCRIPT_COMPLETION_SCRIPT}")"
TARGET_HOME="$HOME"

# shellcheck source=../lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=../lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"

usage() {
    cat <<'EOF'
Usage: scripts/completion/install.sh [common flags]

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

log_info "Installing NXCTL bash completion..."

cleanup_bashrc_completion() {
    if [[ -f "${TARGET_HOME}/.bashrc" ]]; then
        tmp_file="$(mktemp)"
        (grep -v -E "nxctl-completion\\.bash|nxscript-completion\\.bash|ctfs-back-completion\\.bash" "${TARGET_HOME}/.bashrc" || true) > "${tmp_file}"
        mv "${tmp_file}" "${TARGET_HOME}/.bashrc"
        if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
            chown "$SUDO_USER" "${TARGET_HOME}/.bashrc" 2>/dev/null || true
        fi
    fi
}

if [[ ! -f "${NXCTL_COMPLETION_SCRIPT}" ]]; then
    die "Completion script not found at ${NXCTL_COMPLETION_SCRIPT}"
fi

if [[ ! -f "${NXSCRIPT_COMPLETION_SCRIPT}" ]]; then
    die "Completion script not found at ${NXSCRIPT_COMPLETION_SCRIPT}"
fi

chmod +x "${NXCTL_COMPLETION_SCRIPT}" "${NXSCRIPT_COMPLETION_SCRIPT}"
cleanup_bashrc_completion

if [[ -d "/etc/bash_completion.d" ]] && [[ $EUID -eq 0 ]]; then
    run_cmd --label "Installing nxctl completion" cp "${NXCTL_COMPLETION_SCRIPT}" /etc/bash_completion.d/nxctl
    run_cmd --label "Installing nxscript completion" cp "${NXSCRIPT_COMPLETION_SCRIPT}" /etc/bash_completion.d/nxscript
    log_ok "Installed system-wide to /etc/bash_completion.d/nxctl"
    log_ok "Installed system-wide to /etc/bash_completion.d/nxscript"
else
    if [[ -d "${TARGET_HOME}/.bash_completion.d" ]]; then
        run_cmd --label "Installing nxctl completion" cp "${NXCTL_COMPLETION_SCRIPT}" "${TARGET_HOME}/.bash_completion.d/nxctl"
        run_cmd --label "Installing nxscript completion" cp "${NXSCRIPT_COMPLETION_SCRIPT}" "${TARGET_HOME}/.bash_completion.d/nxscript"
        if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
            chown "$SUDO_USER" "${TARGET_HOME}/.bash_completion.d/nxctl" 2>/dev/null || true
            chown "$SUDO_USER" "${TARGET_HOME}/.bash_completion.d/nxscript" 2>/dev/null || true
        fi
        log_ok "Installed for current user to ${TARGET_HOME}/.bash_completion.d/nxctl"
        log_ok "Installed for current user to ${TARGET_HOME}/.bash_completion.d/nxscript"
    elif [[ -f "${TARGET_HOME}/.bashrc" ]]; then
        echo "" >> "${TARGET_HOME}/.bashrc"
        echo "# NXCTL bash completion" >> "${TARGET_HOME}/.bashrc"
        echo "source ${ABS_NXCTL_COMPLETION_SCRIPT}" >> "${TARGET_HOME}/.bashrc"
        echo "source ${ABS_NXSCRIPT_COMPLETION_SCRIPT}" >> "${TARGET_HOME}/.bashrc"
        if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
            chown "$SUDO_USER" "${TARGET_HOME}/.bashrc" 2>/dev/null || true
        fi
        log_ok "Added completion to ${TARGET_HOME}/.bashrc"
    else
        log_warn "Could not find .bashrc or .bash_completion.d"
        echo "Please manually source:"
        echo "  ${ABS_NXCTL_COMPLETION_SCRIPT}"
        echo "  ${ABS_NXSCRIPT_COMPLETION_SCRIPT}"
    fi
fi

echo ""
log_ok "Installation complete."
echo "Restart your shell or run:"
echo "  source ${ABS_NXCTL_COMPLETION_SCRIPT}"
echo "  source ${ABS_NXSCRIPT_COMPLETION_SCRIPT}"
