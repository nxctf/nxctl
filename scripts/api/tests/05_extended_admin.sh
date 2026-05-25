#!/usr/bin/env bash

api_register_test 5 "extended/admin actions" "Checks restart/extend shapes plus optional sync/global admin actions when enabled."

api_test_5() {
  if [[ -z "$API_ADMIN_SECRET" ]]; then
    skip "API_ADMIN_SECRET not configured; skipping extended/admin checks"
    return 0
  fi

  make_request "POST /up without all=true" admin POST "/up" "400"
  make_request "POST /down without all=true" admin POST "/down" "400"

  make_request "POST /up/${CHALLENGE} for extended checks" client POST "/up/${CHALLENGE_ENC}" "200" "$MUTATION_CURL_TIMEOUT"
  make_request "POST /extend/${CHALLENGE}" client POST "/extend/${CHALLENGE_ENC}" "200,400,429"
  make_request "POST /restart/${CHALLENGE}" client POST "/restart/${CHALLENGE_ENC}" "200,429" "$MUTATION_CURL_TIMEOUT"
  make_request "GET /test?name=${CHALLENGE} after up" client GET "/test?name=${CHALLENGE_ENC}" "200"
  make_request "POST /down/${CHALLENGE} cleanup" admin POST "/down/${CHALLENGE_ENC}" "200" "$MUTATION_CURL_TIMEOUT"

  if [[ "$RUN_SYNC" == "1" ]]; then
    make_request "POST /sync" admin POST "/sync" "200" "$SYNC_CURL_TIMEOUT"
  else
    skip "RUN_SYNC=0; set RUN_SYNC=1 to test /sync"
  fi

  if [[ "$RUN_ADMIN_GLOBAL" == "1" ]]; then
    make_request "POST /up?all=true" admin POST "/up?all=true" "200" "$GLOBAL_CURL_TIMEOUT"
    make_request "GET /status after global up" client GET "/status" "200"
    make_request "POST /down?all=true" admin POST "/down?all=true" "200" "$GLOBAL_CURL_TIMEOUT"
  else
    skip "RUN_ADMIN_GLOBAL=0; set RUN_ADMIN_GLOBAL=1 to test /up?all=true and /down?all=true"
  fi
}
