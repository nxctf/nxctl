#!/bin/bash
# Uninstall script for CTFS Back bash completion

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETION_SCRIPT="${SCRIPT_DIR}/ctfs-back-completion.bash"

echo "Uninstalling CTFS Back bash completion..."

if [[ -f "/etc/bash_completion.d/ctfs-back" ]]; then
    rm -f /etc/bash_completion.d/ctfs-back
    echo "✓ Removed system-wide completion"
fi

if [[ -f "${HOME}/.bash_completion.d/ctfs-back" ]]; then
    rm -f "${HOME}/.bash_completion.d/ctfs-back"
    echo "✓ Removed user completion file"
fi

if [[ -f "${HOME}/.bashrc" ]] && [[ -f "${COMPLETION_SCRIPT}" ]]; then
    if grep -q "ctfs-back-completion.bash" "${HOME}/.bashrc"; then
        tmp_file="$(mktemp)"
        grep -v "ctfs-back-completion.bash" "${HOME}/.bashrc" > "${tmp_file}"
        mv "${tmp_file}" "${HOME}/.bashrc"
        echo "✓ Removed source line from ${HOME}/.bashrc"
    fi
fi

echo ""
echo "Uninstall complete!"
