#!/usr/bin/env bash
# Builds the macOS release: dist/GAIA.app
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

echo "==> Building frontend"
(cd web && npm ci && npm run build)

echo "==> Installing release dependencies"
uv pip install -e ".[release]"

echo "==> Running PyInstaller"
rm -rf build dist
uv run pyinstaller packaging/gaia.spec --noconfirm

echo "==> Done: dist/GAIA.app"
