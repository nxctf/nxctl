#!/usr/bin/env bash

API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$API_DIR/../.." && pwd)"

# shellcheck source=../lib/log.sh
source "$PROJECT_DIR/scripts/lib/log.sh"

declare -ga API_TEST_IDS=()
declare -gA API_TEST_NAMES=()
declare -gA API_TEST_DESCS=()

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
API_PID=""
LAST_BODY=""
LAST_STATUS=""
API_READY=0
ENV_SOURCE=""
RESET="$RST"

api_register_test() {
  local id="$1"
  local name="$2"
  local desc="$3"

  API_TEST_IDS+=("$id")
  API_TEST_NAMES["$id"]="$name"
  API_TEST_DESCS["$id"]="$desc"
}

api_load_dotenv() {
  local env_file="$PROJECT_DIR/.env"
  local line key value

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  ENV_SOURCE="$env_file"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue

    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"

    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$env_file"
}

api_init_config() {
  api_load_dotenv

  API_URL="${API_URL:-http://127.0.0.1:8000}"
  API_HOST="${API_HOST:-127.0.0.1}"
  API_PORT="${API_PORT:-8000}"
  CHALLENGE="${CHALLENGE:-simplee}"

  API_TOKEN="${API_TOKEN:-${NXCTL_API_TOKEN:-}}"
  API_ADMIN_SECRET="${API_ADMIN_SECRET:-${NXCTL_API_ADMIN_SECRET:-}}"
  CHALLENGE_KEY="${CHALLENGE_KEY:-${NXCTL_CHALLENGE_KEY:-}}"

  START_API="${START_API:-0}"
  RUN_ADMIN_GLOBAL="${RUN_ADMIN_GLOBAL:-0}"
  RUN_SYNC="${RUN_SYNC:-0}"
  CURL_TIMEOUT="${CURL_TIMEOUT:-30}"
  MUTATION_CURL_TIMEOUT="${MUTATION_CURL_TIMEOUT:-300}"
  GLOBAL_CURL_TIMEOUT="${GLOBAL_CURL_TIMEOUT:-300}"
  SYNC_CURL_TIMEOUT="${SYNC_CURL_TIMEOUT:-120}"

  CHALLENGE_ENC="$(urlencode "$CHALLENGE")"
}

api_load_tests() {
  local test_file
  API_TEST_IDS=()
  API_TEST_NAMES=()
  API_TEST_DESCS=()

  for test_file in "$API_DIR/tests/"*.sh; do
    # shellcheck source=/dev/null
    source "$test_file"
  done
}

api_list_tests() {
  local id
  api_load_tests

  section "Available API Tests"
  for id in "${API_TEST_IDS[@]}"; do
    printf "%s. %s\n" "$id" "${API_TEST_NAMES[$id]}"
    printf "   %s\n" "${API_TEST_DESCS[$id]}"
  done
  echo
  echo "Run examples:"
  echo "  nxscript api test 1"
  echo "  nxscript api test 1 4"
  echo "  nxscript api test all"
}

api_has_test() {
  local wanted="$1"
  local id
  for id in "${API_TEST_IDS[@]}"; do
    [[ "$id" == "$wanted" ]] && return 0
  done
  return 1
}

api_selected_tests() {
  local selected=()
  local arg part

  for arg in "$@"; do
    if [[ "$arg" == "all" ]]; then
      printf "%s\n" "${API_TEST_IDS[@]}"
      return 0
    fi

    IFS=',' read -ra parts <<< "$arg"
    for part in "${parts[@]}"; do
      [[ -z "$part" ]] && continue
      if ! api_has_test "$part"; then
        die "Unknown API test: $part"
      fi
      selected+=("$part")
    done
  done

  printf "%s\n" "${selected[@]}"
}

section() {
  printf "\n%s%s%s\n" "$BOLD" "$1" "$RESET"
  printf "%s\n" "----------------------------------------------------------------"
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf "%s[PASS]%s %s\n" "$GREEN" "$RESET" "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf "%s[FAIL]%s %s\n" "$RED" "$RESET" "$1"
}

skip() {
  SKIP_COUNT=$((SKIP_COUNT + 1))
  printf "%s[SKIP]%s %s\n" "$YELLOW" "$RESET" "$1"
}

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote
print(quote(sys.argv[1], safe=""))
PY
}

pretty_json() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool 2>/dev/null || cat
  else
    cat
  fi
}

expected_matches() {
  local actual="$1"
  local expected_csv="$2"
  local expected
  IFS=',' read -ra expected <<< "$expected_csv"
  for code in "${expected[@]}"; do
    if [[ "$actual" == "$code" ]]; then
      return 0
    fi
  done
  return 1
}

make_request() {
  local label="$1"
  local auth="$2"
  local method="$3"
  local path="$4"
  local expected="$5"
  local timeout="${6:-$CURL_TIMEOUT}"
  local url="${API_URL}${path}"
  local body_file
  body_file="$(mktemp)"

  local args=(
    --silent
    --show-error
    --max-time "$timeout"
    --output "$body_file"
    --write-out "%{http_code}"
    --request "$method"
  )

  case "$auth" in
    public)
      ;;
    client)
      [[ -n "$API_TOKEN" ]] && args+=(--header "Authorization: Bearer ${API_TOKEN}")
      [[ -n "$CHALLENGE_KEY" ]] && args+=(--header "X-NXCTL-Challenge-Key: ${CHALLENGE_KEY}")
      ;;
    client-x)
      [[ -n "$API_TOKEN" ]] && args+=(--header "X-NXCTL-Token: ${API_TOKEN}")
      [[ -n "$CHALLENGE_KEY" ]] && args+=(--header "X-NXCTL-Challenge-Key: ${CHALLENGE_KEY}")
      ;;
    admin)
      [[ -n "$API_TOKEN" ]] && args+=(--header "Authorization: Bearer ${API_TOKEN}")
      [[ -n "$API_ADMIN_SECRET" ]] && args+=(--header "X-NXCTL-Admin-Secret: ${API_ADMIN_SECRET}")
      ;;
    admin-only)
      [[ -n "$API_ADMIN_SECRET" ]] && args+=(--header "X-NXCTL-Admin-Secret: ${API_ADMIN_SECRET}")
      ;;
    wrong-admin)
      [[ -n "$API_TOKEN" ]] && args+=(--header "Authorization: Bearer ${API_TOKEN}")
      args+=(--header "X-NXCTL-Admin-Secret: definitely-wrong")
      ;;
    wrong-client)
      args+=(--header "Authorization: Bearer definitely-wrong")
      ;;
    *)
      fail "internal script error: unknown auth mode '$auth'"
      rm -f "$body_file"
      return 1
      ;;
  esac

  local status
  if ! status="$(curl "${args[@]}" "$url" 2>"${body_file}.err")"; then
    LAST_STATUS="curl-error"
    LAST_BODY="$(cat "${body_file}.err")"
    fail "$label -> curl failed"
    printf "%s\n" "$LAST_BODY"
    rm -f "$body_file" "${body_file}.err"
    return 1
  fi

  LAST_STATUS="$status"
  LAST_BODY="$(cat "$body_file")"

  if expected_matches "$status" "$expected"; then
    pass "$label -> HTTP $status"
  else
    fail "$label -> expected HTTP $expected, got $status"
  fi

  if [[ -n "$LAST_BODY" ]]; then
    printf "%s\n" "$LAST_BODY" | pretty_json | sed 's/^/  /'
  else
    printf "  %s(empty response)%s\n" "$DIM" "$RESET"
  fi

  rm -f "$body_file" "${body_file}.err"
}

assert_no_secret_leak() {
  local label="$1"
  local leaked=0

  [[ -n "$API_TOKEN" ]] && printf "%s" "$LAST_BODY" | grep -Fq "$API_TOKEN" && leaked=1
  [[ -n "$API_ADMIN_SECRET" ]] && printf "%s" "$LAST_BODY" | grep -Fq "$API_ADMIN_SECRET" && leaked=1

  if [[ "$leaked" -eq 0 ]]; then
    pass "$label did not leak configured secrets"
  else
    fail "$label leaked a configured secret in response body"
  fi
}

wait_for_api() {
  local max_attempts=40
  local attempt=1
  while [[ "$attempt" -le "$max_attempts" ]]; do
    if curl --silent --max-time 2 "${API_URL}/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
    attempt=$((attempt + 1))
  done
  return 1
}

api_cleanup() {
  if [[ -n "$API_PID" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
}

api_prepare() {
  if [[ "$API_READY" -eq 1 ]]; then
    return 0
  fi

  cd "$PROJECT_DIR"
  api_init_config

  if [[ "$START_API" == "1" ]]; then
    section "Starting API"
    NXCTL_API_TOKEN="$API_TOKEN" \
    NXCTL_API_ADMIN_SECRET="$API_ADMIN_SECRET" \
    PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}src" \
      python3 -m nxctl.app api --host "$API_HOST" --port "$API_PORT" >/tmp/nxctl-api-test.log 2>&1 &
    API_PID="$!"
    API_URL="http://${API_HOST}:${API_PORT}"
    trap api_cleanup EXIT
    if wait_for_api; then
      pass "API started at ${API_URL} (pid ${API_PID})"
    else
      fail "API did not become ready at ${API_URL}"
      printf "\nAPI log:\n"
      sed 's/^/  /' /tmp/nxctl-api-test.log 2>/dev/null || true
      exit 1
    fi
  else
    section "API Reachability"
    if wait_for_api; then
      pass "API reachable at ${API_URL}"
    else
      fail "API is not reachable at ${API_URL}"
      printf "\nStart it first, for example:\n"
      printf "  nxctl api --host 127.0.0.1 --port 8000\n"
      printf "or:\n"
      printf "  START_API=1 nxscript api test 1\n"
      exit 1
    fi
  fi

  section "Configuration"
  printf "API_URL=%s\n" "$API_URL"
  printf "CHALLENGE=%s\n" "$CHALLENGE"
  [[ -n "$ENV_SOURCE" ]] && printf "ENV=%s\n" "$ENV_SOURCE"
  [[ -n "$API_TOKEN" ]] && printf "API_TOKEN=%sconfigured%s\n" "$GREEN" "$RESET" || printf "API_TOKEN=%snot set%s\n" "$YELLOW" "$RESET"
  [[ -n "$API_ADMIN_SECRET" ]] && printf "API_ADMIN_SECRET=%sconfigured%s\n" "$GREEN" "$RESET" || printf "API_ADMIN_SECRET=%snot set%s\n" "$YELLOW" "$RESET"
  [[ -n "$CHALLENGE_KEY" ]] && printf "CHALLENGE_KEY=%sconfigured%s\n" "$GREEN" "$RESET" || printf "CHALLENGE_KEY=%snot set%s\n" "$YELLOW" "$RESET"

  API_READY=1
}

api_summary() {
  section "Summary"
  printf "Passed: %s\n" "$PASS_COUNT"
  printf "Failed: %s\n" "$FAIL_COUNT"
  printf "Skipped: %s\n" "$SKIP_COUNT"

  if [[ "$FAIL_COUNT" -gt 0 ]]; then
    exit 1
  fi
}
