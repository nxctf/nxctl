#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_RUNNER="$PROJECT_DIR/scripts/api/run.sh"

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
  exec bash "$API_RUNNER" help
fi

if [[ $# -eq 0 ]]; then
  exec bash "$API_RUNNER" list
fi

exec bash "$API_RUNNER" "$@"
