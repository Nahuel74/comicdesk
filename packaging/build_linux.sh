#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== CBL Maker — Linux Build ==="

# Ensure PyInstaller is installed
python3 -m pip install --quiet pyinstaller

# Clean previous build
rm -rf "$ROOT_DIR/build/cbl-maker" "$ROOT_DIR/dist/cbl-maker"

# Build
pyinstaller "$SCRIPT_DIR/cbl-maker.spec" --clean --noconfirm

# Verify
if [ ! -f "$ROOT_DIR/dist/cbl-maker" ]; then
    echo "ERROR: dist/cbl-maker not found" >&2
    exit 1
fi

SIZE=$(du -h "$ROOT_DIR/dist/cbl-maker" | cut -f1)
echo "OK: dist/cbl-maker ($SIZE)"
