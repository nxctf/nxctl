#!/usr/bin/env bash

api_register_test 4 "simple lifecycle" "Starts one challenge, inspects it, checks status, then stops it for cleanup."

api_test_4() {
  if [[ -z "$API_ADMIN_SECRET" ]]; then
    skip "API_ADMIN_SECRET is required so this test can clean up with /down/${CHALLENGE}"
    return 0
  fi

  make_request "POST /up/${CHALLENGE}" client POST "/up/${CHALLENGE_ENC}" "200" "$MUTATION_CURL_TIMEOUT"
  assert_no_secret_leak "POST /up/${CHALLENGE}"
  make_request "GET /inspect/${CHALLENGE} after up" client GET "/inspect/${CHALLENGE_ENC}" "200"
  make_request "GET /status after up" client GET "/status" "200"
  make_request "POST /down/${CHALLENGE}" admin POST "/down/${CHALLENGE_ENC}" "200" "$MUTATION_CURL_TIMEOUT"
}
