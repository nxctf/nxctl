#!/bin/bash
# Bash completion for CTFS Back CLI

_ctfs_back_find_root() {
    local script_dir=""

    if [[ -n "${BASH_SOURCE[0]}" ]]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || script_dir=""
    fi

    if [[ -n "${script_dir}" ]]; then
        if [[ -f "${script_dir}/../app.py" ]]; then
            (cd "${script_dir}/.." 2>/dev/null && pwd)
            return 0
        fi
        if [[ -f "${script_dir}/app.py" ]]; then
            echo "${script_dir}"
            return 0
        fi
    fi

    if [[ -f "./app.py" ]]; then
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

    local python_bin="${PYTHON:-python3}"
    if [[ ! -f "${app_root}/app.py" ]]; then
        return 0
    fi

    (cd "${app_root}" && "${python_bin}" ./app.py list 2>/dev/null \
        | awk 'BEGIN { seen = 0 } /^[[:space:]]*Name[[:space:]]+/ { seen = 1; next } seen && NF && $1 !~ /^-+$/ { print $1 }' \
        | tr -d '\r')
}

_ctfs_back_filter_used_names() {
    local available_names="$1"
    shift

    local used_names=" $* "
    local filtered_names=""

    for name in ${available_names}; do
        if [[ "${used_names}" != *" ${name} "* ]]; then
            filtered_names="${filtered_names} ${name}"
        fi
    done

    echo "${filtered_names}"
}

_ctfs_back_completion() {
    local cur prev cmd
    COMPREPLY=()

    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmd="${COMP_WORDS[1]}"

    local commands="sync list inspect add remove enable disable up down restart status export unexport exports clean purge prune"
    local provider_names="ngrok localtunnel pinggy"

    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
        return 0
    fi

    case "${cmd}" in
        sync)
            ;;
        list)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "-a --all" -- "${cur}") )
            fi
            ;;
        inspect|remove|down|restart|status|unexport)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                if [[ -n "${challenges}" ]]; then
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi
            ;;
        up)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                if [[ -n "${challenges}" ]]; then
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi
            ;;
        enable|disable)
            local challenges
            challenges="$(_ctfs_back_get_challenges)"
            if [[ -n "${challenges}" ]]; then
                local used_names=()
                local i
                for ((i=2; i<COMP_CWORD; i++)); do
                    used_names+=("${COMP_WORDS[i]}")
                done
                challenges="$(_ctfs_back_filter_used_names "${challenges}" "${used_names[@]}")"
                if [[ -n "${challenges}" ]]; then
                    COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                fi
            fi
            ;;
        add)
            if [[ ${COMP_CWORD} -eq 5 ]]; then
                if [[ "${prev}" == "--type" ]]; then
                    COMPREPLY=( $(compgen -W "http tcp" -- "${cur}") )
                fi
            elif [[ ${COMP_CWORD} -eq 6 ]]; then
                if [[ "${prev}" == "--type" ]]; then
                    COMPREPLY=( $(compgen -W "http tcp" -- "${cur}") )
                fi
        purge)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                local candidates="--all"
                if [[ -n "${challenges}" ]]; then
                    candidates="${challenges} ${candidates}"
                fi
                COMPREPLY=( $(compgen -W "${candidates}" -- "${cur}") )
            fi
            ;;
            fi
            ;;
        export)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                local candidates="${provider_names}"
                if [[ -n "${challenges}" ]]; then
                    candidates="${candidates} ${challenges}"
                fi
                COMPREPLY=( $(compgen -W "${candidates}" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 3 ]]; then
                if [[ " ${provider_names} " == *" ${prev} "* ]]; then
                    local challenges
                    challenges="$(_ctfs_back_get_challenges)"
                    if [[ -n "${challenges}" ]]; then
                        COMPREPLY=( $(compgen -W "${challenges}" -- "${cur}") )
                    fi
                fi
            fi
            ;;
        exports)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "--all" -- "${cur}") )
            fi
            ;;
        clean)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local challenges
                challenges="$(_ctfs_back_get_challenges)"
                local candidates="--data --image --volume"
                if [[ -n "${challenges}" ]]; then
                    candidates="${challenges} ${candidates}"
                fi
                COMPREPLY=( $(compgen -W "${candidates}" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 3 ]]; then
                COMPREPLY=( $(compgen -W "--data --image --volume" -- "${cur}") )
            fi
            ;;
        prune)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "--provider" -- "${cur}") )
            elif [[ ${COMP_CWORD} -eq 3 ]]; then
                if [[ "${prev}" == "--provider" ]]; then
                    COMPREPLY=( $(compgen -W "ngrok localtunnel pinggy" -- "${cur}") )
                fi
            fi
            ;;
    esac

    return 0
}

complete -F _ctfs_back_completion ./app.py
complete -F _ctfs_back_completion app.py
complete -F _ctfs_back_completion ctfs-back
