#!/usr/bin/env bash

api_register_test 1 "read-only smoke" "Checks public root plus read-only challenge/status endpoints."

api_test_1() {
  make_request "GET /" public GET "/" "200"
  assert_no_secret_leak "GET /"
  make_request "GET /list" client GET "/list" "200"
  assert_no_secret_leak "GET /list"
  make_request "GET /challenges" client GET "/challenges" "200"
  make_request "GET /status" client GET "/status" "200"
  make_request "GET /inspect/${CHALLENGE}" client GET "/inspect/${CHALLENGE_ENC}" "200,404"
  make_request "GET /test?name=${CHALLENGE}" client GET "/test?name=${CHALLENGE_ENC}" "200,404"
}
