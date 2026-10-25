#!/usr/bin/env sh
# Free Proxy Browser — Cross-Platform Launcher for macOS (Apple Silicon ARM64 / Intel x64) & Linux (x64 / ARM64)
set -e

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/free_proxy_browser.py" "$@"
elif command -v python >/dev/null 2>&1; then
    exec python "$SCRIPT_DIR/free_proxy_browser.py" "$@"
else
    echo "[!] Python 3.9+ is required to run Free Proxy Browser." >&2
    exit 1
fi
