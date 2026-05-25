#!/usr/bin/env bash

SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=log.sh
source "$SCRIPT_LIB_DIR/log.sh"

confirm() {
    local prompt="${1:-Continue?}"
    local answer

    if [[ ! -t 0 ]]; then
        return 1
    fi

    printf "%s [y/N] " "$prompt"
    if ! read -r answer; then
        return 1
    fi

    [[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" || "$answer" == "YES" ]]
}

prompt_input() {
    local prompt_text="$1"
    local default_value="${2:-}"
    local input
    local suffix=""

    if [[ ! -t 0 ]]; then
        printf "%s\n" "$default_value"
        return 0
    fi

    if [[ -n "$default_value" ]]; then
        suffix=" ($default_value)"
    fi

    read -r -p " |_ $prompt_text$suffix: " input
    printf "%s\n" "${input:-$default_value}"
}
