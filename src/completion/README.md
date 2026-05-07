# ⌨️ Bash Completion for ctfc

Enhance your terminal experience with smart tab-completion for **ctfc**.

## ✨ Features
- **Instant Commands**: Complete all `ctfc` subcommands.
- **Dynamic Challenge Detection**: Directly queries the SQLite database for lightning-fast results.
- **Provider Autocomplete**: Complete tunnel providers (`ngrok`, `localtunnel`, `pinggy`).
- **Flag Support**: Autocomplete for flags like `--watch` and `--type`.

## 🚀 Installation
The completion is automatically installed when you run `./setup.sh install`.

To install manually:
```bash
chmod +x install.sh
./install.sh
source ~/.bashrc
```

## 🗑️ Removal
```bash
chmod +x uninstall.sh
./uninstall.sh
```
