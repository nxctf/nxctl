#!/usr/bin/env bash

# Parse nxscript common flags from any argv position.
#
# Results:
#   NXSCRIPT_POSITIONAL_ARGS - argv without common flags
#   NXSCRIPT_HELP            - 1 when -h/--help was present
#   NXSCRIPT_VERBOSE         - exported as 1 when -v/--verbose was present
#   NXSCRIPT_NO_SPINNER      - exported as 1 when --no-spinner was present
#   NXCTL_PROJECT_DIR        - exported when PROJECT_DIR is available

NXSCRIPT_POSITIONAL_ARGS=()
NXSCRIPT_HELP=0

parse_common_flags() {
    NXSCRIPT_POSITIONAL_ARGS=()
    NXSCRIPT_HELP=0

    local passthrough=0
    local arg

    for arg in "$@"; do
        if [[ "$passthrough" -eq 1 ]]; then
            NXSCRIPT_POSITIONAL_ARGS+=("$arg")
            continue
        fi

        case "$arg" in
            --)
                passthrough=1
                ;;
            -v|--verbose)
                export NXSCRIPT_VERBOSE=1
                ;;
            --no-spinner)
                export NXSCRIPT_NO_SPINNER=1
                ;;
            -h|--help)
                NXSCRIPT_HELP=1
                ;;
            *)
                NXSCRIPT_POSITIONAL_ARGS+=("$arg")
                ;;
        esac
    done

    export NXSCRIPT_VERBOSE="${NXSCRIPT_VERBOSE:-0}"
    export NXSCRIPT_NO_SPINNER="${NXSCRIPT_NO_SPINNER:-0}"

    if [[ -n "${PROJECT_DIR:-}" ]]; then
        export NXCTL_PROJECT_DIR="$PROJECT_DIR"
    fi
}

set_common_positionals() {
    set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"
}
