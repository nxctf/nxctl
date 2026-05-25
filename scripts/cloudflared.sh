#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND_NAME="${NXCF_COMMAND_NAME:-$0}"
DEFAULT_TUNNEL="${NXCF_TUNNEL:-nxctl}"
DEFAULT_DOMAIN="${NXCF_DOMAIN:-nxctf.my.id}"
SUBDOMAIN_PREFIX="${NXCF_SUBDOMAIN_PREFIX:-nxctl}"

TUNNEL="$DEFAULT_TUNNEL"
COUNT=""
DOMAIN="$DEFAULT_DOMAIN"

STATE_DIR="${NXCF_STATE_DIR:-$HOME/.cloudflared/nxcloudflare}"
SUBDOMAIN_FILE=""
LEGACY_STATE_FILE=""

# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"
# shellcheck source=lib/prompt.sh
source "$PROJECT_DIR/scripts/lib/prompt.sh"

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

ACTION="${1:-}"

set_subdomain_file() {
  SUBDOMAIN_FILE="${NXCF_SUBDOMAIN_FILE:-$STATE_DIR/$DOMAIN.subdomain}"
  LEGACY_STATE_FILE="$STATE_DIR/$TUNNEL.hosts"
}

generate_subdomain() {
  local hash
  hash="$(openssl rand -hex 5)"
  echo "$SUBDOMAIN_PREFIX-$hash"
}

get_uuid() {
  command -v cloudflared >/dev/null 2>&1 || return 0
  cloudflared tunnel list 2>/dev/null | awk -v name="$TUNNEL" '$2 == name {print $1; exit}' || true
}

tunnel_exists() {
  command -v cloudflared >/dev/null 2>&1 || return 1
  cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$TUNNEL"
}

get_tunnel_created() {
  command -v cloudflared >/dev/null 2>&1 || return 0
  cloudflared tunnel list 2>/dev/null | awk -v name="$TUNNEL" '$1 ~ /^[0-9a-f-]{36}$/ && $2 == name {print $3; exit}' || true
}

get_tunnel_connections() {
  command -v cloudflared >/dev/null 2>&1 || return 0
  cloudflared tunnel list 2>/dev/null | awk -v name="$TUNNEL" '
    $1 ~ /^[0-9a-f-]{36}$/ && $2 == name {
      for (i = 4; i <= NF; i++) {
        printf "%s%s", (i == 4 ? "" : " "), $i
      }
      print ""
      exit
    }
  ' || true
}

print_available_tunnels() {
  command -v cloudflared >/dev/null 2>&1 || return 0

  local tunnels
  tunnels="$(
    cloudflared tunnel list 2>/dev/null |
    awk '$1 ~ /^[0-9a-f-]{36}$/ {print "  - " $2}' ||
    true
  )"

  if [[ -n "$tunnels" ]]; then
    echo "Available tunnels:"
    echo "$tunnels"
  fi
}

validate_count() {
  if [[ -z "$COUNT" ]]; then
    echo "COUNT wajib diisi"
    echo "Usage: $COMMAND_NAME subdomain create 15 [nxctf.my.id]"
    exit 1
  fi

  if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
    echo "COUNT harus angka positif"
    exit 1
  fi
}

create_subdomains() {
  validate_count
  mkdir -p "$STATE_DIR"
  set_subdomain_file

  if ! [[ "$SUBDOMAIN_PREFIX" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]]; then
    echo "NXCF_SUBDOMAIN_PREFIX must be a valid DNS label prefix" >&2
    exit 1
  fi

  if [[ "${#SUBDOMAIN_PREFIX}" -gt 52 ]]; then
    echo "NXCF_SUBDOMAIN_PREFIX is too long; keep it at 52 characters or less" >&2
    exit 1
  fi

  if ! command -v openssl >/dev/null 2>&1; then
    die "openssl tidak ditemukan, dibutuhkan untuk generate subdomain random"
  fi

  if [[ -s "$SUBDOMAIN_FILE" ]]; then
    local existing_count
    existing_count="$(grep -cve '^[[:space:]]*$' "$SUBDOMAIN_FILE" || true)"
    echo "[!] Subdomain file already exists: $SUBDOMAIN_FILE"
    echo "[!] Existing subdomains: $existing_count"

    if ! confirm "Overwrite and generate new subdomains?"; then
      echo "[OK] Keeping existing subdomains"
      list_subdomains
      return 0
    fi
  fi

  local tmp_file="$SUBDOMAIN_FILE.tmp.$$"
  : > "$tmp_file"

  echo "[+] Generating $COUNT subdomains for $DOMAIN"
  for ((i=0; i<COUNT; i++)); do
    local host
    host="$(generate_subdomain).$DOMAIN"
    echo "$host" >> "$tmp_file"
    echo "[+] $host"
  done

  mv "$tmp_file" "$SUBDOMAIN_FILE"

  echo
  echo "[OK] Saved subdomains to: $SUBDOMAIN_FILE"
}

require_subdomains() {
  set_subdomain_file

  if [[ ! -s "$SUBDOMAIN_FILE" && -s "$LEGACY_STATE_FILE" ]]; then
    mkdir -p "$STATE_DIR"
    cp "$LEGACY_STATE_FILE" "$SUBDOMAIN_FILE"
    echo "[*] Imported existing subdomains from: $LEGACY_STATE_FILE"
  fi

  if [[ ! -s "$SUBDOMAIN_FILE" ]]; then
    echo "Subdomain file not found: $SUBDOMAIN_FILE" >&2
    echo "Run first: $COMMAND_NAME subdomain create 15 $DOMAIN" >&2
    exit 1
  fi
}

list_subdomains() {
  require_subdomains

  echo "========== subdomains =========="
  echo "File: $SUBDOMAIN_FILE"
  echo
  cat "$SUBDOMAIN_FILE"
  echo "================================"
}

delete_tunnel_only() {
  if tunnel_exists; then
    echo "[-] tunnel: $TUNNEL"
    run --label "Deleting tunnel $TUNNEL" cloudflared tunnel delete -f "$TUNNEL"
  else
    ok "Tunnel not found: $TUNNEL"
    print_available_tunnels
  fi
}

create_tunnel() {
  require_subdomains
  mkdir -p "$HOME/.cloudflared"

  if tunnel_exists; then
    ok "Tunnel already exists, reusing: $TUNNEL"
  else
    info "Creating tunnel: $TUNNEL"
    run --label "Creating tunnel $TUNNEL" cloudflared tunnel create "$TUNNEL"
  fi

  local uuid
  local creds
  uuid="$(get_uuid)"
  creds="$HOME/.cloudflared/$uuid.json"

  if [[ ! -f "$creds" ]]; then
    echo "Credential JSON not found: $creds"
    exit 1
  fi

  echo "[+] Creating/updating DNS routes from: $SUBDOMAIN_FILE"
  while IFS= read -r host || [[ -n "$host" ]]; do
    [[ -z "$host" ]] && continue
    echo "[+] $host"
    run --label "Routing $host" cloudflared tunnel route dns --overwrite-dns "$TUNNEL" "$host"
  done < "$SUBDOMAIN_FILE"

  echo
  echo "========== config.yml =========="
  cat <<EOF
tunnels:
  cloudflare:
    enabled: true
    tunnel_name: $TUNNEL
    credentials_file: ~/.cloudflared/$uuid.json
    subdomains:
EOF

  while IFS= read -r host || [[ -n "$host" ]]; do
    [[ -z "$host" ]] && continue
    echo "      - $host"
  done < "$SUBDOMAIN_FILE"

  echo "================================"
  ok "Done"
}

print_config() {
  require_subdomains

  local uuid
  uuid="$(get_uuid)"

  if [[ -z "$uuid" ]]; then
    echo "Tunnel not found: $TUNNEL" >&2
    echo "Run first: $COMMAND_NAME tunnel create $TUNNEL $DOMAIN" >&2
    exit 1
  fi

  cat <<EOF
tunnels:
  cloudflare:
    enabled: true
    tunnel_name: $TUNNEL
    credentials_file: ~/.cloudflared/$uuid.json
    subdomains:
EOF

  while IFS= read -r host || [[ -n "$host" ]]; do
    [[ -z "$host" ]] && continue
    echo "      - $host"
  done < "$SUBDOMAIN_FILE"
}

delete_tunnel() {
  delete_tunnel_only
  set_subdomain_file

  echo
  echo "[OK] Subdomain file kept:"
  echo "  $SUBDOMAIN_FILE"
  echo
  echo "Subdomain names are intentionally kept. Next create will reuse these names."
}

list_tunnels() {
  if ! command -v cloudflared >/dev/null 2>&1; then
    die "cloudflared not found"
  fi

  local output
  if ! output="$(cloudflared tunnel list 2>/dev/null)"; then
    echo "Failed to list tunnels. Run manually: cloudflared tunnel list" >&2
    return 1
  fi

  local rows
  rows="$(
    awk '
      $1 ~ /^[0-9a-f-]{36}$/ {
        connections = ""
        for (i = 4; i <= NF; i++) {
          connections = connections (i == 4 ? "" : " ") $i
        }
        printf "  %-20s %-36s %-20s %s\n", $2, $1, $3, connections
      }
    ' <<<"$output"
  )"

  if [[ -z "$rows" ]]; then
    echo "No tunnels found"
    return 0
  fi

  echo "========== tunnels =========="
  printf "  %-20s %-36s %-20s %s\n" "NAME" "UUID" "CREATED" "CONNECTIONS"
  echo "$rows"
  echo "============================="
}

info_tunnel() {
  local uuid
  local created
  local connections
  uuid="$(get_uuid)"

  echo "========== tunnel info =========="
  echo "Name           : $TUNNEL"

  if [[ -n "$uuid" ]]; then
    created="$(get_tunnel_created)"
    connections="$(get_tunnel_connections)"
    echo "Status         : exists"
    echo "UUID           : $uuid"
    echo "Target         : $uuid.cfargotunnel.com"
    echo "Created        : ${created:-unknown}"
    echo "Connections    : ${connections:-none}"
  else
    echo "Status         : not found"
    print_available_tunnels
  fi

  echo "================================="
}

usage() {
  echo "Usage:"
  echo "  $COMMAND_NAME [common flags] create <nxctl> <count> [nxctf.my.id]"
  echo "  $COMMAND_NAME [common flags] delete <nxctl> [nxctf.my.id]"
  echo "  $COMMAND_NAME [common flags] subdomain create 15 [nxctf.my.id]"
  echo "  $COMMAND_NAME [common flags] subdomain list [nxctf.my.id]"
  echo "  $COMMAND_NAME [common flags] tunnel create [nxctl] [nxctf.my.id]"
  echo "  $COMMAND_NAME [common flags] tunnel list"
  echo "  $COMMAND_NAME [common flags] tunnel info <nxctl>"
  echo "  $COMMAND_NAME [common flags] tunnel delete [nxctl] [nxctf.my.id]"
  echo "  $COMMAND_NAME [common flags] config [nxctl] [nxctf.my.id]"
  echo
  echo "Common flags: -v, --verbose, --no-spinner, -h, --help"
}

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
  usage
  exit 0
fi

case "$ACTION" in
  create)
    TUNNEL="${2:-$DEFAULT_TUNNEL}"
    COUNT="${3:-}"
    DOMAIN="${4:-$DEFAULT_DOMAIN}"
    create_subdomains
    create_tunnel
    ;;
  delete)
    TUNNEL="${2:-$DEFAULT_TUNNEL}"
    DOMAIN="${3:-$DEFAULT_DOMAIN}"
    delete_tunnel
    ;;
  subdomain)
    case "${2:-}" in
      create)
        COUNT="${3:-}"
        DOMAIN="${4:-$DEFAULT_DOMAIN}"
        create_subdomains
        ;;
      list)
        DOMAIN="${3:-$DEFAULT_DOMAIN}"
        list_subdomains
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  tunnel)
    case "${2:-}" in
      create)
        TUNNEL="${3:-$DEFAULT_TUNNEL}"
        DOMAIN="${4:-$DEFAULT_DOMAIN}"
        create_tunnel
        ;;
      list)
        list_tunnels
        ;;
      info)
        if [[ -z "${3:-}" ]]; then
          echo "Tunnel name wajib diisi"
          echo "Usage: $COMMAND_NAME tunnel info <nxctl>"
          exit 1
        fi
        TUNNEL="${3:-}"
        info_tunnel
        ;;
      delete)
        TUNNEL="${3:-$DEFAULT_TUNNEL}"
        DOMAIN="${4:-$DEFAULT_DOMAIN}"
        delete_tunnel
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  config)
    TUNNEL="${2:-$DEFAULT_TUNNEL}"
    DOMAIN="${3:-$DEFAULT_DOMAIN}"
    print_config
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
