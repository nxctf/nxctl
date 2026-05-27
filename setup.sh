#!/usr/bin/env bash
set -euo pipefail

# Compatibility bootstrap for historical setup.sh commands.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=scripts/lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

COMMAND="${1:-help}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$COMMAND" in
  nxbcl)
    exec bash "$PROJECT_DIR/nxbcl/setup.sh" "$@"
    ;;
  install)
    if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
      exec bash "$PROJECT_DIR/scripts/install.sh" --help
    fi
    exec bash "$PROJECT_DIR/scripts/install.sh" "$@"
    ;;
  uninstall)
    if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
      exec bash "$PROJECT_DIR/scripts/uninstall.sh" --help
    fi
    exec bash "$PROJECT_DIR/scripts/uninstall.sh" "$@"
    ;;
  help|--help|-h)
    echo "Usage: $0 [install|uninstall|nxbcl]"
    echo
    echo "Preferred command after install:"
    echo "  nxscript update"
    echo "  nxscript delete"
    echo "  nxscript service start|stop|restart|status"
    echo
    echo "NXBCL launcher:"
    echo "  $0 nxbcl install"
    echo "  $0 nxbcl frontend-install"
    echo "  $0 nxbcl frontend-build"
    echo "  $0 nxbcl uninstall"
    ;;
  *)
    if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
      echo "Usage: $0 [install|uninstall|nxbcl]"
      exit 0
    fi
    echo "Unknown setup command: $COMMAND" >&2
    echo "Usage: $0 [install|uninstall|nxbcl]" >&2
    exit 1
    ;;
esac
