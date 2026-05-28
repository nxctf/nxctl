#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${NXBCL_BIN_DIR:-$HOME/.local/bin}"
COMMAND="${1:-help}"

ensure_node22() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

  if ! command -v nvm >/dev/null 2>&1; then
    if [ -s "$NVM_DIR/nvm.sh" ]; then
      . "$NVM_DIR/nvm.sh"
    fi
  fi

  if ! command -v nvm >/dev/null 2>&1; then
    echo "Installing nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    . "$NVM_DIR/nvm.sh"
  fi

  echo "Installing Node.js 22..."
  nvm install 22
  nvm alias default 22
  nvm use 22

  echo "Node: $(node -v)"
  echo "npm: $(npm -v)"
}

case "$COMMAND" in
  install)
    ensure_node22
    python3 -m pip install -r "$PROJECT_DIR/requirements.txt"
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/nxbcl" <<EOF
#!/usr/bin/env bash
cd "$PROJECT_DIR"
exec python3 app.py "\$@"
EOF
    chmod +x "$BIN_DIR/nxbcl"
    echo "Installed nxbcl command to $BIN_DIR/nxbcl"
    echo "Frontend source is in nxbcl/src/frontend."
    echo "Build it with: cd $PROJECT_DIR/src/frontend && npm install && npm run build"
    case ":$PATH:" in
      *":$BIN_DIR:"*) ;;
      *)
        echo
        echo "Add this to your shell if nxbcl is not found:"
        echo "  export PATH=\"$BIN_DIR:\$PATH\""
        ;;
    esac
    ;;
  frontend-install)
    cd "$PROJECT_DIR/src/frontend"
    npm install
    ;;
  frontend-build)
    cd "$PROJECT_DIR/src/frontend"
    npm run build
    ;;
  uninstall)
    rm -f "$BIN_DIR/nxbcl"
    echo "Removed $BIN_DIR/nxbcl"
    ;;
  help|--help|-h)
    echo "Usage: bash nxbcl/setup.sh install|frontend-install|frontend-build|uninstall"
    echo
    echo "After install:"
    echo "  nxbcl init-db"
    echo "  nxbcl sync --dry-run"
    echo "  nxbcl challenges"
    echo "  nxbcl up        # start compose stack and seed RPC lease"
    echo "  nxbcl ps        # show compose status and lease time"
    echo "  nxbcl down      # stop compose stack"
    echo "  nxbcl ps --kill # stop compose and clear runtime data"
    echo "  nxbcl serve --host 0.0.0.0 --port 8080"
    echo
    echo "Frontend:"
    echo "  bash nxbcl/setup.sh frontend-install"
    echo "  bash nxbcl/setup.sh frontend-build"
    echo
    echo "Frontend source: nxbcl/src/frontend/"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    echo "Usage: bash nxbcl/setup.sh install|frontend-install|frontend-build|uninstall" >&2
    exit 1
    ;;
esac
