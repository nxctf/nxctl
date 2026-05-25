#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
TUNNEL="${2:-nxctl}"
COUNT="${3:-15}"
DOMAIN="${4:-nxctf.my.id}"

STATE_DIR="$HOME/.cloudflared/nxcloudflare"
STATE_FILE="$STATE_DIR/$TUNNEL.hosts"
mkdir -p "$STATE_DIR" "$HOME/.cloudflared"

letters() {
  local count="$1"
  local i
  for ((i=0; i<count; i++)); do
    printf "\\$(printf '%03o' $((97+i)))"
    echo
  done
}

get_uuid() {
  cloudflared tunnel list | awk -v name="$TUNNEL" '$2 == name {print $1; exit}'
}

delete_all() {
  echo "[*] Deleting DNS routes for tunnel: $TUNNEL"

  if [[ -f "$STATE_FILE" ]]; then
    while read -r host; do
      [[ -z "$host" ]] && continue
      echo "[-] route: $host"
      cloudflared tunnel route dns delete "$TUNNEL" "$host" 2>/dev/null || \
      cloudflared tunnel route dns delete "$host" 2>/dev/null || true
    done < "$STATE_FILE"
    rm -f "$STATE_FILE"
  fi

  if cloudflared tunnel list | awk '{print $2}' | grep -qx "$TUNNEL"; then
    echo "[-] tunnel: $TUNNEL"
    cloudflared tunnel delete -f "$TUNNEL"
  fi

  echo "[✓] Deleted"
}

create_all() {
  if [[ "$COUNT" -gt 26 ]]; then
    echo "COUNT max 26 untuk mode a-z"
    exit 1
  fi

  if cloudflared tunnel list | awk '{print $2}' | grep -qx "$TUNNEL"; then
    echo "[!] Tunnel $TUNNEL already exists, deleting first..."
    delete_all
  fi

  echo "[+] Creating tunnel: $TUNNEL"
  cloudflared tunnel create "$TUNNEL"

  UUID="$(get_uuid)"
  CREDS="$HOME/.cloudflared/$UUID.json"

  if [[ ! -f "$CREDS" ]]; then
    echo "Credential JSON not found: $CREDS"
    exit 1
  fi

  : > "$STATE_FILE"

  echo "[+] Creating DNS routes..."
  while read -r sub; do
    host="$sub.$DOMAIN"
    echo "[+] $host"
    cloudflared tunnel route dns "$TUNNEL" "$host"
    echo "$host" >> "$STATE_FILE"
  done < <(letters "$COUNT")

  echo
  echo "========== config.yml =========="
  cat <<EOF
cloudflare:
  enabled: true
  tunnel_name: $TUNNEL
  credentials_file: ~/.cloudflared/$UUID.json
  subdomains:
EOF

  while read -r host; do
    echo "    - $host"
  done < "$STATE_FILE"

  echo "================================"
  echo "[✓] Done"
}

case "$ACTION" in
  create)
    create_all
    ;;
  delete)
    delete_all
    ;;
  *)
    echo "Usage:"
    echo "  ./nxcloudflare create edge 15 nxctf.my.id"
    echo "  ./nxcloudflare delete edge"
    exit 1
    ;;
esac
