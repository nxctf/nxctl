#!/usr/bin/env bash

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RST=$'\033[0m'
    BOLD=$'\033[1m'
    DIM=$'\033[2m'
    BLUE=$'\033[1;34m'
    CYAN=$'\033[1;36m'
    GREEN=$'\033[1;32m'
    YELLOW=$'\033[1;33m'
    RED=$'\033[1;31m'
else
    RST=""
    BOLD=""
    DIM=""
    BLUE=""
    CYAN=""
    GREEN=""
    YELLOW=""
    RED=""
fi

NC="$RST"
