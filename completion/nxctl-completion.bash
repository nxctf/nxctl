#!/bin/bash
# Bash completion for NXCTL.

_nxctl_find_root() {
    local script_dir=""
    if [[ -n "${BASH_SOURCE[0]}" ]]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || script_dir=""
    fi

    if [[ -n "${script_dir}" ]]; then
        if [[ -f "${script_dir}/../src/nxctl/app.py" ]]; then
            (cd "${script_dir}/.." 2>/dev/null && pwd)
            return 0
        fi
        if [[ -f "${script_dir}/../app.py" ]]; then
            if [[ "$(basename "$(cd "${script_dir}/.." 2>/dev/null && pwd)")" == "nxctl" ]] \
                && [[ "$(basename "$(cd "${script_dir}/../.." 2>/dev/null && pwd)")" == "src" ]]; then
                (cd "${script_dir}/../../.." 2>/dev/null && pwd)
            else
                (cd "${script_dir}/../.." 2>/dev/null && pwd)
            fi
            return 0
        fi
        if [[ -f "${script_dir}/nxctl/app.py" ]]; then
            echo "${script_dir}"
            return 0
        fi
    fi

    if [[ -f "./nxctl/app.py" ]]; then
        pwd
        return 0
    fi
    if [[ -f "./src/nxctl/app.py" ]]; then
        pwd
        return 0
    fi
    echo ""
}

_nxctl_get_challenges() {
    local app_root
    app_root="$(_nxctl_find_root)"
    if [[ -z "${app_root}" ]]; then
        return 0
    fi

    local db_path="${app_root}/data/nxctl.db"
    if [[ -f "${db_path}" ]] && command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "${db_path}" "SELECT name FROM challenges" 2>/dev/null
        return 0
    fi

    local python_bin="python3"
    if [[ -f "${app_root}/src/nxctl/app.py" ]]; then
        (cd "${app_root}" && PYTHONPATH="${app_root}/src${PYTHONPATH:+:${PYTHONPATH}}" "${python_bin}" -m nxctl.app list 2>/dev/null \
            | awk 'BEGIN { seen = 0 } /^[[:space:]]*Name[[:space:]]+/ { seen = 1; next } seen && NF && $1 !~ /^-+$/ { print $1 }' \
            | tr -d '\r')
    elif [[ -f "${app_root}/nxctl/app.py" ]]; then
        (cd "${app_root}" && "${python_bin}" -m nxctl.app list 2>/dev/null \
            | awk 'BEGIN { seen = 0 } /^[[:space:]]*Name[[:space:]]+/ { seen = 1; next } seen && NF && $1 !~ /^-+$/ { print $1 }' \
            | tr -d '\r')
    fi
}

_nxctl_completion() {
    local cur prev cmd
    COMPREPLY=()

    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmd="${COMP_WORDS[1]}"

    local commands="sync list inspect add remove up down restart status extend daemon api export unexport exports test ps"
    local provider_names="ngrok localtunnel pinggy cloudflare bore"

    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
        return 0
    fi

    case "${cmd}" in
        sync)
            ;;
        list)
            if [[ "${cur}" == -* ]]; then
                COMPREPLY=( $(compgen -W "-a --all -k --key" -- "${cur}") )
            fi
            ;;
        inspect|remove|up|down|status|extend|unexport)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_nxctl_get_challenges)"
                if [[ "${cmd}" == "down" || "${cmd}" == "up" ]]; then
                    challenges="--all ${challenges}"
                fi
                if [[ -n "${challenges}" ]]; then
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi

            if [[ "${cmd}" == "status" ]] && [[ "${cur}" == -* ]]; then
                COMPREPLY=( $(compgen -W "-w --watch" -- "${cur}") )
            fi
            if [[ "${cmd}" == "down" ]] && [[ "${cur}" == -* ]]; then
                COMPREPLY=( $(compgen -W "--all" -- "${cur}") )
            fi
            if [[ "${cmd}" == "up" ]] && [[ "${cur}" == -* ]]; then
                COMPREPLY=( $(compgen -W "--all" -- "${cur}") )
            fi
            ;;
        restart)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_nxctl_get_challenges)"
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
            if [[ ${COMP_CWORD} -eq 5 ]]; then
                COMPREPLY=( $(compgen -W "--type" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 6 && "${prev}" == "--type" ]]; then
                COMPREPLY=( $(compgen -W "http tcp" -- "${cur}") )
            fi
            ;;
        export)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_nxctl_get_challenges)"
                local candidates="${provider_names} ${challenges}"
                COMPREPLY=( $(compgen -W "${candidates}" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 3 ]]; then
                if [[ " ${provider_names} " == *" ${prev} "* ]]; then
                    local challenges
                    challenges="$(_nxctl_get_challenges)"
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi
            ;;
        exports)
            ;;
        ps)
            COMPREPLY=( $(compgen -W "--kill" -- "${cur}") )
            ;;
    esac

    return 0
}

complete -F _nxctl_completion nxctl
