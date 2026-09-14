#!/usr/bin/env pwsh
# Builds the Windows release: dist/GAIA.exe
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Building frontend"
Push-Location web
npm ci
npm run build
Pop-Location

Write-Host "==> Installing release dependencies"
uv pip install -e ".[release]"

Write-Host "==> Running PyInstaller"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
uv run pyinstaller packaging/gaia.spec --noconfirm

Write-Host "==> Done: dist/GAIA.exe"
