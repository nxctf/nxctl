#!/bin/bash
# Uninstall script for NXCTL bash completion.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETION_SCRIPT="${SCRIPT_DIR}/nxctl-completion.bash"

echo "Uninstalling NXCTL bash completion..."

if [[ -f "/etc/bash_completion.d/nxctl" ]]; then
    rm -f /etc/bash_completion.d/nxctl
    echo "Removed system-wide completion"
fi

if [[ -f "${HOME}/.bash_completion.d/nxctl" ]]; then
    rm -f "${HOME}/.bash_completion.d/nxctl"
    echo "Removed user completion file"
fi

if [[ -f "${HOME}/.bashrc" ]] && [[ -f "${COMPLETION_SCRIPT}" ]]; then
    if grep -q "nxctl-completion.bash" "${HOME}/.bashrc"; then
        tmp_file="$(mktemp)"
        grep -v "nxctl-completion.bash" "${HOME}/.bashrc" > "${tmp_file}"
        mv "${tmp_file}" "${HOME}/.bashrc"
        echo "Removed source line from ${HOME}/.bashrc"
    fi
    if grep -q "ctfs-back-completion.bash" "${HOME}/.bashrc"; then
        tmp_file="$(mktemp)"
        grep -v "ctfs-back-completion.bash" "${HOME}/.bashrc" > "${tmp_file}"
        mv "${tmp_file}" "${HOME}/.bashrc"
        echo "Removed legacy source line from ${HOME}/.bashrc"
    fi
fi

echo ""
echo "Uninstall complete."
