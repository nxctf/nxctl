#!/usr/bin/env bash
# Bash completion for NXCTL helper command.

_nxscript_completion() {
    local cur command subcommand arg_index
    local common_flags="-v --verbose --no-spinner -h --help"
    local top_commands="uninstall update api cloudflared service"
    local words=()
    local word

    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"

    for word in "${COMP_WORDS[@]:1:COMP_CWORD}"; do
        case "$word" in
            -v|--verbose|--no-spinner|-h|--help)
                ;;
            *)
                words+=("$word")
                ;;
        esac
    done

    command="${words[0]:-}"
    subcommand="${words[1]:-}"
    arg_index="${#words[@]}"

    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$common_flags" -- "$cur") )
        return 0
    fi

    if [[ -z "$command" ]]; then
        COMPREPLY=( $(compgen -W "$common_flags $top_commands" -- "$cur") )
        return 0
    fi

    case "$command" in
        service)
            if [[ "$arg_index" -eq 1 ]]; then
                COMPREPLY=( $(compgen -W "$common_flags start stop restart status install uninstall install-start" -- "$cur") )
            fi
            ;;
        completion)
            if [[ "$arg_index" -eq 1 ]]; then
                COMPREPLY=( $(compgen -W "$common_flags install uninstall" -- "$cur") )
            fi
            ;;
        api)
            if [[ "$arg_index" -eq 1 ]]; then
                COMPREPLY=( $(compgen -W "$common_flags 1 2 3 4 5 all" -- "$cur") )
            fi
            ;;
        cloudflared|cloudflare)
            if [[ "$arg_index" -eq 1 ]]; then
                COMPREPLY=( $(compgen -W "$common_flags create delete subdomain tunnel config" -- "$cur") )
                return 0
            fi

            case "$subcommand" in
                create)
                    if [[ "$arg_index" -eq 2 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags nxctl" -- "$cur") )
                    fi
                    ;;
                delete|config)
                    if [[ "$arg_index" -eq 2 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags nxctl" -- "$cur") )
                    elif [[ "$arg_index" -eq 3 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags nxctf.my.id" -- "$cur") )
                    fi
                    ;;
                subdomain)
                    if [[ "$arg_index" -eq 2 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags create list" -- "$cur") )
                    elif [[ "$arg_index" -eq 4 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags nxctf.my.id" -- "$cur") )
                    fi
                    ;;
                tunnel)
                    if [[ "$arg_index" -eq 2 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags create list info delete" -- "$cur") )
                    elif [[ "$arg_index" -eq 3 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags nxctl" -- "$cur") )
                    elif [[ "$arg_index" -eq 4 ]]; then
                        COMPREPLY=( $(compgen -W "$common_flags nxctf.my.id" -- "$cur") )
                    fi
                    ;;
            esac
            ;;
    esac

    return 0
}

complete -F _nxscript_completion nxscript
