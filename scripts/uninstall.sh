#!/usr/bin/env bash
set -euo pipefail

# Remove installed command wrappers and shell completion. Runtime data is kept.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NXCTL_BIN_TARGET="/usr/local/bin/nxctl"
NXSCRIPT_BIN_TARGET="/usr/local/bin/nxscript"

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"

usage() {
    cat <<'EOF'
Usage: scripts/uninstall.sh [common flags]

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

info "Uninstalling NXCTL command wrappers..."

bash "$PROJECT_DIR/scripts/completion/uninstall.sh" 2>/dev/null || true

if [ -f "$NXCTL_BIN_TARGET" ]; then
    run --label "Removing $NXCTL_BIN_TARGET" sudo rm -f "$NXCTL_BIN_TARGET"
    echo "  -> Removed $NXCTL_BIN_TARGET"
fi

if [ -f "$NXSCRIPT_BIN_TARGET" ]; then
    run --label "Removing $NXSCRIPT_BIN_TARGET" sudo rm -f "$NXSCRIPT_BIN_TARGET"
    echo "  -> Removed $NXSCRIPT_BIN_TARGET"
fi

ok "NXCTL uninstalled."
echo "config.yml and data/ were kept."
echo "Service units are managed separately with 'bash scripts/service.sh uninstall'."
