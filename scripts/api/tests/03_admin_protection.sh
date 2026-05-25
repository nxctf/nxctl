#!/usr/bin/env bash

api_register_test 3 "admin protection" "Checks dangerous/global endpoints reject missing or wrong admin secrets."

api_test_3() {
  make_request "POST /down/${CHALLENGE} without admin secret" client POST "/down/${CHALLENGE_ENC}" "403"
  make_request "POST /up?all=true without admin secret" client POST "/up?all=true" "403"
  make_request "POST /down?all=true without admin secret" client POST "/down?all=true" "403"
  make_request "POST /sync without admin secret" client POST "/sync" "403"

  if [[ -n "$API_ADMIN_SECRET" ]]; then
    make_request "POST /down/${CHALLENGE} with wrong admin secret" wrong-admin POST "/down/${CHALLENGE_ENC}" "403"
  else
    skip "API_ADMIN_SECRET not configured; skipping wrong-admin check"
  fi
}
