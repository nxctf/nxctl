#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${NXBCL_BIN_DIR:-$HOME/.local/bin}"
COMMAND="${1:-help}"

case "$COMMAND" in
  install)
    python3 -m pip install -r "$PROJECT_DIR/nxbcl/requirements.txt"
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/nxbcl" <<EOF
#!/usr/bin/env bash
cd "$PROJECT_DIR"
exec python3 -m nxbcl.cli.main "\$@"
EOF
    chmod +x "$BIN_DIR/nxbcl"
    echo "Installed nxbcl command to $BIN_DIR/nxbcl"
    echo "Frontend source is in nxbcl/frontend."
    echo "Build it with: cd $PROJECT_DIR/nxbcl/frontend && npm install && npm run build"
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
    cd "$PROJECT_DIR/nxbcl/frontend"
    npm install
    ;;
  frontend-build)
    cd "$PROJECT_DIR/nxbcl/frontend"
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
    echo "  nxbcl serve --host 0.0.0.0 --port 8080"
    echo
    echo "Frontend:"
    echo "  bash nxbcl/setup.sh frontend-install"
    echo "  bash nxbcl/setup.sh frontend-build"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    echo "Usage: bash nxbcl/setup.sh install|frontend-install|frontend-build|uninstall" >&2
    exit 1
    ;;
esac
