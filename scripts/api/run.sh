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
    die "nxscript api test is no longer supported; use nxscript api [1|2|3|4|5|all]"
    ;;
  help|--help|-h)
    api_list_tests
    ;;
  *)
    api_load_tests
    mapfile -t selected < <(api_selected_tests "$COMMAND" "$@")
    api_prepare

    for id in "${selected[@]}"; do
      test_func="api_test_${id}"
      section "Test ${id}: ${API_TEST_NAMES[$id]}"
      printf "%s\n" "${API_TEST_DESCS[$id]}"
      start_pass="$PASS_COUNT"
      start_fail="$FAIL_COUNT"
      start_skip="$SKIP_COUNT"
      "$test_func"
      printf "Test %s summary: %s passed, %s failed, %s skipped\n" \
        "$id" \
        "$((PASS_COUNT - start_pass))" \
        "$((FAIL_COUNT - start_fail))" \
        "$((SKIP_COUNT - start_skip))"
    done

    api_summary
    ;;
esac
