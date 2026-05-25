# Bash Completion for NXCTL

Enhance your terminal experience with smart tab-completion for `nxctl`.

## Features

- Complete all `nxctl` subcommands.
- Suggest challenge names from the SQLite database when available.
- Complete tunnel providers: `ngrok`, `localtunnel`, and `pinggy`.
- Complete common flags such as `--watch`, `--type`, `--host`, and `--port`.
- Complete `nxscript` helper commands and nested maintenance subcommands.

## Installation

The completion is automatically installed when you run:

```bash
./setup.sh install
```

To install manually:

```bash
nxscript completion install
source ~/.bashrc
```

To test in the current shell:

```bash
source scripts/completion/nxctl-completion.bash
source scripts/completion/nxscript-completion.bash
```

## Removal

```bash
nxscript completion uninstall
```
