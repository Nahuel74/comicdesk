#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== ComicDesk — Linux Build ==="

# Ensure PyInstaller is installed
python3 -m pip install --quiet pyinstaller

# Clean previous build
rm -rf "$ROOT_DIR/build/comicdesk" "$ROOT_DIR/dist/comicdesk"

# Build
pyinstaller "$SCRIPT_DIR/comicdesk.spec" --clean --noconfirm

# Verify
if [ ! -f "$ROOT_DIR/dist/comicdesk" ]; then
    echo "ERROR: dist/comicdesk not found" >&2
    exit 1
fi

SIZE=$(du -h "$ROOT_DIR/dist/comicdesk" | cut -f1)
echo "OK: dist/comicdesk ($SIZE)"
