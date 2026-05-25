#!/usr/bin/env bash

api_register_test 2 "client token headers" "Checks Authorization bearer, X-NXCTL-Token, wrong token, and missing token behavior."

api_test_2() {
  if [[ -z "$API_TOKEN" ]]; then
    skip "API_TOKEN not configured; skipping token-negative checks"
    return 0
  fi

  make_request "GET /status with Authorization bearer" client GET "/status" "200"
  make_request "GET /status with X-NXCTL-Token" client-x GET "/status" "200"
  make_request "GET /status with wrong client token" wrong-client GET "/status" "401"
  make_request "GET /status without client token" public GET "/status" "401"
}
