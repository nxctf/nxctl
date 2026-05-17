# Bash Completion for NXCTL

Enhance your terminal experience with smart tab-completion for `nxctl`.

## Features

- Complete all `nxctl` subcommands.
- Suggest challenge names from the SQLite database when available.
- Complete tunnel providers: `ngrok`, `localtunnel`, and `pinggy`.
- Complete common flags such as `--watch`, `--type`, `--host`, and `--port`.

## Installation

The completion is automatically installed when you run:

```bash
./setup.sh install
```

To install manually:

```bash
chmod +x install.sh
./install.sh
source ~/.bashrc
```

## Removal

```bash
chmod +x uninstall.sh
./uninstall.sh
```
