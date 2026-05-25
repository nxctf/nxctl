#!/usr/bin/env bash

SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=colors.sh
source "$SCRIPT_LIB_DIR/colors.sh"

log_info() {
    printf "%s[*]%s %s\n" "$BLUE" "$RST" "$*"
}

log_ok() {
    printf "%s[OK]%s %s\n" "$GREEN" "$RST" "$*"
}

log_warn() {
    printf "%s[!]%s %s\n" "$YELLOW" "$RST" "$*" >&2
}

log_err() {
    printf "%s[x]%s %s\n" "$RED" "$RST" "$*" >&2
}

die() {
    log_err "$*"
    exit 1
}

info() { log_info "$@"; }
ok() { log_ok "$@"; }
warn() { log_warn "$@"; }
err() { log_err "$@"; }
