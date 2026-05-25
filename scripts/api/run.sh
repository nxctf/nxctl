#!/usr/bin/env bash
set -euo pipefail

API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$API_DIR/common.sh"

COMMAND="${1:-list}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$COMMAND" in
  list)
    api_list_tests
    ;;
  test)
    api_load_tests
    if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
      api_list_tests
      exit 0
    fi

    mapfile -t selected < <(api_selected_tests "$@")
    api_prepare

    for id in "${selected[@]}"; do
      test_func="api_test_${id}"
      section "Test ${id}: ${API_TEST_NAMES[$id]}"
      printf "%s\n" "${API_TEST_DESCS[$id]}"
      "$test_func"
    done

    api_summary
    ;;
  help|--help|-h)
    cat <<'EOF'
Usage:
  nxscript api list
  nxscript api test
  nxscript api test all
  nxscript api test 1 3
EOF
    ;;
  *)
    die "Unknown api runner command: $COMMAND"
    ;;
esac
