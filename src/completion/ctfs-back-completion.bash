#!/bin/bash
# Bash completion for CTF Orchestration Engine (ctf-orch)

_ctfs_back_find_root() {
    local script_dir=""
    if [[ -n "${BASH_SOURCE[0]}" ]]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || script_dir=""
    fi

    if [[ -n "${script_dir}" ]]; then
        # Check parent or current for app.py
        if [[ -f "${script_dir}/../src/app.py" ]]; then
            (cd "${script_dir}/.." 2>/dev/null && pwd)
            return 0
        fi
        if [[ -f "${script_dir}/src/app.py" ]]; then
            echo "${script_dir}"
            return 0
        fi
    fi

    if [[ -f "./src/app.py" ]]; then
        pwd
        return 0
    fi
    echo ""
}

_ctfs_back_get_challenges() {
    local app_root
    app_root="$(_ctfs_back_find_root)"
    if [[ -z "${app_root}" ]]; then
        return 0
    fi

    # Try getting from SQLite directly for speed
    local db_path="${app_root}/data/ctf-orch.db"
    if [[ -f "${db_path}" ]] && command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "${db_path}" "SELECT name FROM challenges" 2>/dev/null
        return 0
    fi

    # Fallback to app.py list if sqlite fails
    local python_bin="python3"
    if [[ -f "${app_root}/src/app.py" ]]; then
        (cd "${app_root}" && "${python_bin}" src/app.py list 2>/dev/null \
            | awk 'BEGIN { seen = 0 } /^[[:space:]]*Name[[:space:]]+/ { seen = 1; next } seen && NF && $1 !~ /^-+$/ { print $1 }' \
            | tr -d '\r')
    fi
}

_ctfs_back_completion() {
    local cur prev cmd
    COMPREPLY=()

    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmd="${COMP_WORDS[1]}"

    # Updated command list to match app.py
    local commands="sync list inspect add remove up down restart status extend daemon api export unexport exports"
    local provider_names="ngrok localtunnel pinggy"

    # Top-level commands
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
        return 0
    fi

    case "${cmd}" in
        sync)
            # No common arguments for sync
            ;;
        list)
            # No common arguments for list usually
            ;;
        inspect|remove|up|down|status|extend|unexport)
            # Commands that take a challenge name as first argument
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                if [[ -n "${challenges}" ]]; then
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi

            # Special flags for status
            if [[ "${cmd}" == "status" ]] && [[ "${cur}" == -* ]]; then
                COMPREPLY=( $(compgen -W "-w --watch" -- "${cur}") )
            fi
            ;;
        restart)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                if [[ -n "${challenges}" ]]; then
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            else
                COMPREPLY=( $(compgen -W "--container --provider" -- "${cur}") )
            fi
            ;;
        daemon)
            COMPREPLY=( $(compgen -W "--interval --with-api --host --port" -- "${cur}") )
            ;;
        api)
            COMPREPLY=( $(compgen -W "--host --port" -- "${cur}") )
            ;;
        add)
            # add <name> <path> <port> [--type {http,tcp}]
            if [[ ${COMP_CWORD} -eq 5 ]]; then
                COMPREPLY=( $(compgen -W "--type" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 6 && "${prev}" == "--type" ]]; then
                COMPREPLY=( $(compgen -W "http tcp" -- "${cur}") )
            fi
            ;;
        export)
            # export [provider] <challenge>
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                local candidates="${provider_names} ${challenges}"
                COMPREPLY=( $(compgen -W "${candidates}" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 3 ]]; then
                # If provider was specified in word 2, suggest challenges in word 3
                if [[ " ${provider_names} " == *" ${prev} "* ]]; then
                    local challenges
                    challenges="$(_ctfs_back_get_challenges)"
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi
            ;;
        exports)
            # No arguments
            ;;
    esac

    return 0
}

# Register completion for various aliases
complete -F _ctfs_back_completion python3 src/app.py
complete -F _ctfs_back_completion python src/app.py
complete -F _ctfs_back_completion ./src/app.py
complete -F _ctfs_back_completion ctfc
