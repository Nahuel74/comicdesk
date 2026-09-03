#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DIST="$ROOT_DIR/dist"

echo "=== CBL Maker — Build Verification ==="

ERRORS=0

# Check binary exists
if [ -f "$DIST/cbl-maker" ]; then
    SIZE=$(stat --format=%s "$DIST/cbl-maker" 2>/dev/null || stat -f%z "$DIST/cbl-maker")
    SIZE_MB=$((SIZE / 1024 / 1024))
    echo "[OK] Linux binary: $SIZE_MB MB"

    if [ "$SIZE_MB" -lt 5 ]; then
        echo "[WARN] Binary suspiciously small — likely missing dependencies"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "[FAIL] dist/cbl-maker not found"
    ERRORS=$((ERRORS + 1))
fi

# Check executable permission
if [ -f "$DIST/cbl-maker" ] && [ ! -x "$DIST/cbl-maker" ]; then
    echo "[WARN] dist/cbl-maker is not executable"
    ERRORS=$((ERRORS + 1))
fi

if [ "$ERRORS" -gt 0 ]; then
    echo "Verification FAILED with $ERRORS error(s)"
    exit 1
fi

echo "All checks passed."
