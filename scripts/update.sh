#!/usr/bin/env bash
set -euo pipefail

# Update the NXCTL repository when remote changes are available, then refresh
# installed command wrappers.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/args.sh
source "$PROJECT_DIR/scripts/lib/args.sh"
# shellcheck source=lib/log.sh
source "$PROJECT_DIR/scripts/lib/log.sh"
# shellcheck source=lib/prompt.sh
source "$PROJECT_DIR/scripts/lib/prompt.sh"
# shellcheck source=lib/spinner.sh
source "$PROJECT_DIR/scripts/lib/spinner.sh"

usage() {
    cat <<'EOF'
Usage: nxscript [common flags] update [options]

Options:
  -y, --yes      Apply available repository update without prompting

Common flags:
  -v, --verbose
  --no-spinner
  -h, --help
EOF
}

is_git_repo() {
    git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

has_local_changes() {
    ! git -C "$PROJECT_DIR" diff --quiet ||
    ! git -C "$PROJECT_DIR" diff --cached --quiet ||
    [[ -n "$(git -C "$PROJECT_DIR" ls-files --others --exclude-standard)" ]]
}

select_update_ref() {
    local upstream_ref
    local branch
    local remote

    upstream_ref="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
    branch="$(git -C "$PROJECT_DIR" branch --show-current 2>/dev/null || true)"

    if [[ -n "$upstream_ref" ]]; then
        printf "%s\n" "$upstream_ref"
        return 0
    fi

    if [[ -z "$branch" ]]; then
        return 1
    fi

    if git -C "$PROJECT_DIR" remote get-url origin >/dev/null 2>&1; then
        remote="origin"
    else
        remote="$(git -C "$PROJECT_DIR" remote | head -n 1)"
    fi

    if [[ -z "$remote" ]]; then
        return 1
    fi

    printf "%s/%s\n" "$remote" "$branch"
    return 0
}

fetch_remote() {
    local update_ref="$1"
    local remote="${update_ref%%/*}"

    if [[ -z "$remote" || "$remote" == "$update_ref" ]]; then
        remote="origin"
    fi

    if ! git -C "$PROJECT_DIR" remote get-url "$remote" >/dev/null 2>&1; then
        remote="$(git -C "$PROJECT_DIR" remote | head -n 1)"
    fi

    if [[ -z "$remote" ]]; then
        return 1
    fi

    run --label "Checking remote repository" git -C "$PROJECT_DIR" fetch --prune "$remote"
}

apply_repository_update() {
    local update_ref
    local counts
    local local_ahead
    local remote_ahead
    local pull_remote
    local pull_branch
    local -a pull_cmd
    local stash_created=0
    local stash_ref=""

    if ! command -v git >/dev/null 2>&1; then
        warn "git not found; skipping repository update check."
        return 0
    fi

    if ! is_git_repo; then
        warn "Project directory is not a git working tree; skipping repository update check."
        return 0
    fi

    update_ref="$(select_update_ref || true)"
    if [[ -z "$update_ref" ]]; then
        warn "No upstream branch found; skipping repository update check."
        return 0
    fi

    if ! fetch_remote "$update_ref"; then
        warn "Could not fetch remote updates; continuing with local wrapper refresh."
        return 0
    fi

    counts="$(git -C "$PROJECT_DIR" rev-list --left-right --count "HEAD...$update_ref" 2>/dev/null || true)"
    if [[ -z "$counts" ]]; then
        warn "Could not compare local branch with $update_ref; skipping repository update."
        return 0
    fi

    read -r local_ahead remote_ahead <<<"$counts"
    local_ahead="${local_ahead:-0}"
    remote_ahead="${remote_ahead:-0}"

    if [[ "$remote_ahead" -eq 0 ]]; then
        ok "Repository is already up to date."
        return 0
    fi

    if [[ "$local_ahead" -gt 0 ]]; then
        warn "Remote has $remote_ahead new commit(s), but local branch also has $local_ahead unpushed commit(s)."
        warn "Skipping automatic pull to avoid merging/rebasing local commits."
        return 0
    fi

    warn "A new NXCTL version is available ($remote_ahead commit(s) behind $update_ref)."
    if [[ "$UPDATE_ASSUME_YES" -ne 1 ]] && ! confirm "Do you want to update now?"; then
        warn "Repository update skipped."
        return 0
    fi

    if has_local_changes; then
        run --label "Stashing local changes" git -C "$PROJECT_DIR" stash push -u -m "nxscript update auto-stash"
        stash_created=1
        stash_ref="stash@{0}"
    fi

    pull_remote="${update_ref%%/*}"
    pull_branch="${update_ref#*/}"
    if [[ -z "$pull_remote" || "$pull_remote" == "$update_ref" || -z "$pull_branch" || "$pull_branch" == "$update_ref" ]]; then
        pull_remote=""
        pull_branch=""
    fi

    if [[ -n "$pull_remote" ]]; then
        pull_cmd=(git -C "$PROJECT_DIR" pull --ff-only "$pull_remote" "$pull_branch")
    else
        pull_cmd=(git -C "$PROJECT_DIR" pull --ff-only)
    fi

    if ! run --label "Pulling repository update" "${pull_cmd[@]}"; then
        if [[ "$stash_created" -eq 1 ]]; then
            warn "Pull failed; restoring stashed local changes."
            git -C "$PROJECT_DIR" stash apply --index "$stash_ref" || git -C "$PROJECT_DIR" stash apply "$stash_ref" || true
        fi
        die "Repository update failed."
    fi

    if [[ "$stash_created" -eq 1 ]]; then
        if run --label "Restoring local changes" git -C "$PROJECT_DIR" stash apply --index "$stash_ref"; then
            ok "Local changes restored from stash. Stash backup kept at $stash_ref."
        else
            warn "Could not fully restore local changes with index; trying normal stash apply."
            if git -C "$PROJECT_DIR" stash apply "$stash_ref"; then
                ok "Local changes restored from stash. Stash backup kept at $stash_ref."
            else
                warn "Stash apply failed. Your backup is still available at $stash_ref."
            fi
        fi
    fi
}

parse_common_flags "$@"
set -- "${NXSCRIPT_POSITIONAL_ARGS[@]}"

if [[ "$NXSCRIPT_HELP" -eq 1 ]]; then
    usage
    exit 0
fi

UPDATE_ASSUME_YES=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)
            UPDATE_ASSUME_YES=1
            ;;
        *)
            die "Unknown update option: $1"
            ;;
    esac
    shift
done

apply_repository_update

info "Removing installed command wrappers..."
bash "$PROJECT_DIR/scripts/uninstall.sh" --wrappers-only

info "Installing updated command wrappers..."
bash "$PROJECT_DIR/scripts/install.sh"

ok "NXCTL update complete."
