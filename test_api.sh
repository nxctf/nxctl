#!/usr/bin/env bash
# Simple testing script for NXCTL API

API_URL="http://localhost:8000"
TOKEN="CTF_FGTE" # Change this to match your .env
CHALLENGE="simplee"

echo "--- Testing Root ---"
curl -s -X GET "$API_URL/" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Challenges List ---"
curl -s -X GET "$API_URL/challenges" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing UP ($CHALLENGE) ---"
curl -s -X POST "$API_URL/up/$CHALLENGE" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Status ---"
curl -s -X GET "$API_URL/status" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Inspect ($CHALLENGE) ---"
curl -s -X GET "$API_URL/inspect/$CHALLENGE" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Extend ($CHALLENGE) ---"
curl -s -X POST "$API_URL/extend/$CHALLENGE" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Restart ($CHALLENGE) ---"
curl -s -X POST "$API_URL/restart/$CHALLENGE" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Down ($CHALLENGE) ---"
curl -s -X POST "$API_URL/down/$CHALLENGE" -H "X-NXCTL-Token: $TOKEN" | jq .

echo -e "\n--- Testing Status ---"
curl -s -X GET "$API_URL/status" -H "X-NXCTL-Token: $TOKEN" | jq .

# Uncomment to test shutdown
# echo -e "\n--- Testing DOWN ($CHALLENGE) ---"
# curl -s -X POST "$API_URL/down/$CHALLENGE" -H "X-NXCTL-Token: $TOKEN" | jq .
