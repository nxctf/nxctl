#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_RUNNER="$PROJECT_DIR/scripts/api/run.sh"

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

COMMAND="${1:-list}"
if [[ $# -gt 0 ]]; then
  shift
fi

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
  cat <<'EOF'
Usage:
  nxscript [common flags] api list
  nxscript [common flags] api test
  nxscript [common flags] api test all
  nxscript [common flags] api test 1 3

Without a test number, 'nxscript api test' lists available tests.
EOF
  exit 0
fi

case "$COMMAND" in
  list)
    exec bash "$API_RUNNER" list "$@"
    ;;
  test)
    exec bash "$API_RUNNER" test "$@"
    ;;
  help)
    cat <<'EOF'
Usage:
  nxscript [common flags] api list
  nxscript [common flags] api test
  nxscript [common flags] api test all
  nxscript [common flags] api test 1 3

Without a test number, 'nxscript api test' lists available tests.
EOF
    ;;
  *)
    echo "Unknown api command: $COMMAND" >&2
    echo "Usage: nxscript api list|test" >&2
    exit 1
    ;;
esac
