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
  --wrappers-only
EOF
}

FORCE_UNINSTALL=0
WRAPPERS_ONLY=0

nxctl_cli() {
    if command -v nxctl >/dev/null 2>&1; then
        printf 'nxctl'
        return 0
    fi

    printf 'python3 %q' "$PROJECT_DIR/app.py"
}

confirm_uninstall() {
    local reply

    if [[ "$FORCE_UNINSTALL" -eq 1 ]]; then
        return 0
    fi

    if [[ ! -t 0 ]]; then
        die "Refusing to uninstall without an interactive terminal. Run it from a shell and confirm the prompt."
    fi

    echo "This will stop all nxctl runtimes, kill nxctl provider processes, and remove command wrappers."
    echo "If the nxctl daemon service exists, it will be stopped, disabled, and removed first."
    printf "Proceed with uninstall? [y/N] "
    read -r reply

    case "$reply" in
        y|Y|yes|YES)
            ;;
        *)
            echo "Uninstall cancelled."
            exit 0
            ;;
    esac
}

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

for arg in "$@"; do
    case "$arg" in
        -y|--yes)
            FORCE_UNINSTALL=1
            ;;
        --wrappers-only)
            WRAPPERS_ONLY=1
            FORCE_UNINSTALL=1
            ;;
    esac
done

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
    usage
    exit 0
fi

confirm_uninstall

info "Uninstalling NXCTL command wrappers..."

if [[ "$WRAPPERS_ONLY" -eq 0 ]]; then
    run --label "Stopping all NXCTL runtimes" bash -lc "$(nxctl_cli) down --all" || true
    run --label "Killing NXCTL provider processes" bash -lc "$(nxctl_cli) ps --kill" || true
fi

if [[ "$WRAPPERS_ONLY" -eq 0 ]]; then
    bash "$PROJECT_DIR/scripts/service.sh" uninstall 2>/dev/null || true
    bash "$PROJECT_DIR/scripts/completion/uninstall.sh" 2>/dev/null || true
fi

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
if [[ "$WRAPPERS_ONLY" -eq 1 ]]; then
    echo "Service and completion were left untouched."
else
    echo "nxctl-daemon was stopped, disabled, and removed if it was installed."
fi
