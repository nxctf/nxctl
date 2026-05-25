#!/usr/bin/env bash

SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=log.sh
source "$SCRIPT_LIB_DIR/log.sh"

_NXSCRIPT_SPINNER_PID=""
_NXSCRIPT_SPINNER_LOG=""

_nxscript_spinner_restore() {
    if [[ "${_NXSCRIPT_STTY_SAVED:-0}" -eq 1 && -t 0 ]]; then
        stty sane 2>/dev/null || true
        _NXSCRIPT_STTY_SAVED=0
    fi
}

_nxscript_spinner_interrupt() {
    local code="${1:-130}"
    if [[ -n "${_NXSCRIPT_SPINNER_PID:-}" ]]; then
        kill "$_NXSCRIPT_SPINNER_PID" 2>/dev/null || true
    fi
    _nxscript_spinner_restore
    [[ -n "${_NXSCRIPT_SPINNER_LOG:-}" ]] && rm -f "$_NXSCRIPT_SPINNER_LOG"
    printf "\n" >&2
    trap - INT TERM
    exit "$code"
}

_nxscript_spinner_flush_input() {
    if [[ -t 0 ]]; then
        while read -r -t 0.01 -n 1 _unused 2>/dev/null; do :; done
    fi
}

run_cmd() {
    local label=""
    local errexit_set=0

    if [[ "${1:-}" == "--label" ]]; then
        label="${2:-}"
        shift 2
    fi

    if [[ $# -eq 0 ]]; then
        die "run_cmd called without a command"
    fi

    [[ $- == *e* ]] && errexit_set=1

    if [[ "${NXSCRIPT_VERBOSE:-0}" == "1" ]]; then
        if [[ -n "$label" ]]; then
            log_info "$label"
        fi
        set +e
        "$@"
        local verbose_exit_code=$?
        if [[ $errexit_set -eq 1 ]]; then
            set -e
        fi
        return "$verbose_exit_code"
    fi

    if [[ "${NXSCRIPT_NO_SPINNER:-0}" == "1" || ! -t 1 ]]; then
        if [[ -n "$label" ]]; then
            log_info "$label"
        fi
        set +e
        "$@"
        local plain_exit_code=$?
        if [[ $errexit_set -eq 1 ]]; then
            set -e
        fi
        if [[ "$plain_exit_code" -eq 0 && -n "$label" ]]; then
            log_ok "$label"
        fi
        return "$plain_exit_code"
    fi

    local log_file
    local pid
    local exit_code
    local start_time
    local duration
    local chars
    local i

    log_file="$(mktemp)"
    _NXSCRIPT_SPINNER_LOG="$log_file"
    start_time="$(date +%s)"
    chars="|/-\\"
    i=0
    _NXSCRIPT_STTY_SAVED=0

    if [[ -t 0 ]]; then
        stty -echo -icanon 2>/dev/null || true
        _NXSCRIPT_STTY_SAVED=1
    fi

    trap '_nxscript_spinner_interrupt 130' INT
    trap '_nxscript_spinner_interrupt 143' TERM

    "$@" >"$log_file" 2>&1 &
    pid=$!
    _NXSCRIPT_SPINNER_PID="$pid"

    while kill -0 "$pid" 2>/dev/null; do
        printf "\r%s[*]%s %s %s" "$YELLOW" "$RST" "${label:-Running}" "${chars:i++%${#chars}:1}"
        sleep 0.1
    done

    set +e
    wait "$pid"
    exit_code=$?
    if [[ $errexit_set -eq 1 ]]; then
        set -e
    fi
    duration=$(($(date +%s) - start_time))

    _nxscript_spinner_restore
    _nxscript_spinner_flush_input
    trap - INT TERM
    _NXSCRIPT_SPINNER_PID=""

    if [[ $exit_code -eq 0 ]]; then
        printf "\r%s[OK]%s %s in %ss\n" "$GREEN" "$RST" "${label:-Done}" "$duration"
        rm -f "$log_file"
    else
        printf "\r%s[x]%s %s failed with exit code %s\n" "$RED" "$RST" "${label:-Command}" "$exit_code" >&2
        if [[ -s "$log_file" ]]; then
            sed 's/^/  /' "$log_file" >&2
        fi
        rm -f "$log_file"
    fi

    return "$exit_code"
}

run() { run_cmd "$@"; }
