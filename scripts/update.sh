#!/usr/bin/env bash
set -euo pipefail

# Refresh installed NXCTL wrappers after the repository has been updated.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

info "Removing installed command wrappers..."
bash "$PROJECT_DIR/scripts/uninstall.sh" --wrappers-only

info "Installing updated command wrappers..."
bash "$PROJECT_DIR/scripts/install.sh"

ok "NXCTL update complete."
