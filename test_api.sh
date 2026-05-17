#!/usr/bin/env bash
#
# Full-ish NXCTL API smoke/security test.
#
# Defaults are safe:
# - Read-only endpoint tests always run.
# - Single challenge mutation tests run only when an admin secret is available,
#   so the script can clean up with /down/{name}.
# - Global/destructive admin tests are opt-in.
#
# Examples:
#   ./test_api.sh
#   API_TOKEN=client123 API_ADMIN_SECRET=aria123 ./test_api.sh
#   CHALLENGE=simplee API_URL=http://127.0.0.1:8000 ./test_api.sh
#   RUN_ADMIN_GLOBAL=1 API_ADMIN_SECRET=aria123 GLOBAL_CURL_TIMEOUT=600 ./test_api.sh
#   RUN_SYNC=1 API_ADMIN_SECRET=aria123 ./test_api.sh
#   START_API=1 API_PORT=8000 API_TOKEN=client123 API_ADMIN_SECRET=aria123 ./test_api.sh

set -Eeuo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
CHALLENGE="${CHALLENGE:-simplee}"

# Both names are accepted for convenience.
API_TOKEN="${API_TOKEN:-${NXCTL_API_TOKEN:-}}"
API_ADMIN_SECRET="${API_ADMIN_SECRET:-${NXCTL_API_ADMIN_SECRET:-}}"

START_API="${START_API:-0}"
RUN_MUTATING="${RUN_MUTATING:-auto}"
RUN_ADMIN_GLOBAL="${RUN_ADMIN_GLOBAL:-0}"
RUN_SYNC="${RUN_SYNC:-0}"
CURL_TIMEOUT="${CURL_TIMEOUT:-30}"
GLOBAL_CURL_TIMEOUT="${GLOBAL_CURL_TIMEOUT:-300}"
SYNC_CURL_TIMEOUT="${SYNC_CURL_TIMEOUT:-120}"

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
API_PID=""
LAST_BODY=""
LAST_STATUS=""

if command -v tput >/dev/null 2>&1 && [ -t 1 ]; then
  BOLD="$(tput bold)"
  DIM="$(tput dim)"
  RED="$(tput setaf 1)"
  GREEN="$(tput setaf 2)"
  YELLOW="$(tput setaf 3)"
  BLUE="$(tput setaf 4)"
  RESET="$(tput sgr0)"
else
  BOLD=""
  DIM=""
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  RESET=""
fi

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
    if [ "$actual" = "$code" ]; then
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
      if [ -n "$API_TOKEN" ]; then
        args+=(--header "Authorization: Bearer ${API_TOKEN}")
      fi
      ;;
    client-x)
      if [ -n "$API_TOKEN" ]; then
        args+=(--header "X-NXCTL-Token: ${API_TOKEN}")
      fi
      ;;
    admin)
      if [ -n "$API_TOKEN" ]; then
        args+=(--header "Authorization: Bearer ${API_TOKEN}")
      fi
      if [ -n "$API_ADMIN_SECRET" ]; then
        args+=(--header "X-NXCTL-Admin-Secret: ${API_ADMIN_SECRET}")
      fi
      ;;
    admin-only)
      if [ -n "$API_ADMIN_SECRET" ]; then
        args+=(--header "X-NXCTL-Admin-Secret: ${API_ADMIN_SECRET}")
      fi
      ;;
    wrong-admin)
      if [ -n "$API_TOKEN" ]; then
        args+=(--header "Authorization: Bearer ${API_TOKEN}")
      fi
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

  if [ -n "$LAST_BODY" ]; then
    printf "%s\n" "$LAST_BODY" | pretty_json | sed 's/^/  /'
  else
    printf "  %s(empty response)%s\n" "$DIM" "$RESET"
  fi

  rm -f "$body_file" "${body_file}.err"
}

assert_no_secret_leak() {
  local label="$1"
  local leaked=0

  if [ -n "$API_TOKEN" ] && printf "%s" "$LAST_BODY" | grep -Fq "$API_TOKEN"; then
    leaked=1
  fi
  if [ -n "$API_ADMIN_SECRET" ] && printf "%s" "$LAST_BODY" | grep -Fq "$API_ADMIN_SECRET"; then
    leaked=1
  fi

  if [ "$leaked" -eq 0 ]; then
    pass "$label did not leak configured secrets"
  else
    fail "$label leaked a configured secret in response body"
  fi
}

wait_for_api() {
  local max_attempts=40
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if curl --silent --max-time 2 "${API_URL}/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
    attempt=$((attempt + 1))
  done
  return 1
}

cleanup() {
  if [ -n "$API_PID" ]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [ "$START_API" = "1" ]; then
  section "Starting API"
  NXCTL_API_TOKEN="$API_TOKEN" \
  NXCTL_API_ADMIN_SECRET="$API_ADMIN_SECRET" \
  PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}src" \
    python3 -m nxctl.app api --host "$API_HOST" --port "$API_PORT" >/tmp/nxctl-api-test.log 2>&1 &
  API_PID="$!"
  API_URL="http://${API_HOST}:${API_PORT}"
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
    printf "  START_API=1 %s\n" "$0"
    exit 1
  fi
fi

CHALLENGE_ENC="$(urlencode "$CHALLENGE")"

section "Configuration"
printf "API_URL=%s\n" "$API_URL"
printf "CHALLENGE=%s\n" "$CHALLENGE"
if [ -n "$API_TOKEN" ]; then
  printf "API_TOKEN=%sconfigured%s\n" "$GREEN" "$RESET"
else
  printf "API_TOKEN=%snot set%s (client-token endpoints may be public if server has no api_token)\n" "$YELLOW" "$RESET"
fi
if [ -n "$API_ADMIN_SECRET" ]; then
  printf "API_ADMIN_SECRET=%sconfigured%s\n" "$GREEN" "$RESET"
else
  printf "API_ADMIN_SECRET=%snot set%s (admin endpoint success tests will be skipped)\n" "$YELLOW" "$RESET"
fi

section "Public Root"
make_request "GET /" public GET "/" "200"
assert_no_secret_leak "GET /"

section "Read-Only Endpoints"
make_request "GET /list" client GET "/list" "200"
assert_no_secret_leak "GET /list"
make_request "GET /challenges" client GET "/challenges" "200"
make_request "GET /status" client GET "/status" "200"
make_request "GET /inspect/${CHALLENGE}" client GET "/inspect/${CHALLENGE_ENC}" "200,404"
make_request "GET /test?name=${CHALLENGE}" client GET "/test?name=${CHALLENGE_ENC}" "200,404"
make_request "POST /test?name=${CHALLENGE} (read-only)" client POST "/test?name=${CHALLENGE_ENC}" "200,404"

if [ -n "$API_TOKEN" ]; then
  section "Client Token Header Modes"
  make_request "GET /status with Authorization bearer" client GET "/status" "200"
  make_request "GET /status with X-NXCTL-Token" client-x GET "/status" "200"
  make_request "GET /status with wrong client token" wrong-client GET "/status" "401"
  make_request "GET /status without client token" public GET "/status" "401"
else
  section "Client Token Header Modes"
  skip "API_TOKEN not provided locally; skipping token-negative checks"
fi

section "Admin Protection Negative Checks"
make_request "POST /down/${CHALLENGE} without admin secret" client POST "/down/${CHALLENGE_ENC}" "403"
make_request "POST /up?all=true without admin secret" client POST "/up?all=true" "403"
make_request "POST /down?all=true without admin secret" client POST "/down?all=true" "403"
make_request "POST /sync without admin secret" client POST "/sync" "403"
if [ -n "$API_ADMIN_SECRET" ]; then
  make_request "POST /down/${CHALLENGE} with wrong admin secret" wrong-admin POST "/down/${CHALLENGE_ENC}" "403"
else
  skip "API_ADMIN_SECRET not provided locally; skipping wrong-admin check"
fi

if [ "$RUN_MUTATING" = "auto" ]; then
  if [ -n "$API_ADMIN_SECRET" ]; then
    RUN_MUTATING="1"
  else
    RUN_MUTATING="0"
  fi
fi

if [ "$RUN_MUTATING" = "1" ]; then
  section "Single Challenge Mutations"
  make_request "POST /up/${CHALLENGE} (client token only)" client POST "/up/${CHALLENGE_ENC}" "200"
  assert_no_secret_leak "POST /up/${CHALLENGE}"
  make_request "POST /extend/${CHALLENGE} (client token only)" client POST "/extend/${CHALLENGE_ENC}" "200,400,429"
  make_request "POST /restart/${CHALLENGE} (no admin secret required)" client POST "/restart/${CHALLENGE_ENC}" "200,429"
  make_request "GET /status after up/restart" client GET "/status" "200"
  make_request "GET /test?name=${CHALLENGE} after up" client GET "/test?name=${CHALLENGE_ENC}" "200"

  if [ -n "$API_ADMIN_SECRET" ]; then
    make_request "POST /down/${CHALLENGE} (admin secret required)" admin POST "/down/${CHALLENGE_ENC}" "200"
  else
    skip "Skipping cleanup down because API_ADMIN_SECRET is not set"
  fi
else
  section "Single Challenge Mutations"
  skip "RUN_MUTATING=${RUN_MUTATING}; set RUN_MUTATING=1 and API_ADMIN_SECRET to test up/restart/down"
fi

if [ -n "$API_ADMIN_SECRET" ]; then
  section "Admin Route Shape Checks"
  make_request "POST /up without all=true" admin POST "/up" "400"
  make_request "POST /down without all=true" admin POST "/down" "400"
else
  section "Admin Route Shape Checks"
  skip "API_ADMIN_SECRET not provided; admin success/shape checks skipped"
fi

if [ "$RUN_SYNC" = "1" ]; then
  section "Admin Sync"
  make_request "POST /sync" admin POST "/sync" "200" "$SYNC_CURL_TIMEOUT"
else
  section "Admin Sync"
  skip "RUN_SYNC=0; set RUN_SYNC=1 to test /sync"
fi

if [ "$RUN_ADMIN_GLOBAL" = "1" ]; then
  section "Global Admin Actions"
  printf "Using GLOBAL_CURL_TIMEOUT=%ss because global up/down can build and export many challenges.\n" "$GLOBAL_CURL_TIMEOUT"
  make_request "POST /up?all=true" admin POST "/up?all=true" "200" "$GLOBAL_CURL_TIMEOUT"
  make_request "GET /status after global up" client GET "/status" "200"
  make_request "POST /down?all=true" admin POST "/down?all=true" "200" "$GLOBAL_CURL_TIMEOUT"
else
  section "Global Admin Actions"
  skip "RUN_ADMIN_GLOBAL=0; set RUN_ADMIN_GLOBAL=1 to test /up?all=true and /down?all=true"
fi

section "Summary"
printf "Passed: %s\n" "$PASS_COUNT"
printf "Failed: %s\n" "$FAIL_COUNT"
printf "Skipped: %s\n" "$SKIP_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi

exit 0
