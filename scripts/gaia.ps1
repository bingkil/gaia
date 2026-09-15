#!/usr/bin/env pwsh
# Start, stop, or restart a packaged GAIA release build, for end users who
# just want to run the app rather than do frontend/backend development. This
# is a single self-contained process serving both the API and the built UI on
# one port - see scripts/dev.ps1 for the separate backend+Vite dev workflow.
#
# Usage:
#   scripts/gaia.ps1 start   [-Port 8000]
#   scripts/gaia.ps1 stop
#   scripts/gaia.ps1 restart [-Port 8000]
#
# GAIA.exe is looked for next to this script first (a standalone release
# download that ships the script alongside the binary), then ..\dist\GAIA.exe
# (a local release build in this repo checkout), then falls back to whatever
# "GAIA" resolves to on PATH (an installed copy).
#
# The packaged entry point (packaging/gaia_app.py) always runs `gaia serve`
# regardless of any arguments passed to the executable, so the port can only
# be set via the GAIA_PORT environment variable. It is auto-bumped past
# anything already listening.

param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart")]
    [string]$Action = "start",

    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir

function Find-GaiaExe {
    foreach ($candidate in @(
            (Join-Path $scriptDir "GAIA.exe"),
            (Join-Path $repoRoot "dist\GAIA.exe")
        )) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    $onPath = Get-Command "GAIA" -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

$exePath = Find-GaiaExe
$exeDir = if ($exePath) { Split-Path -Parent $exePath } else { $repoRoot }
$stateDir = Join-Path $exeDir ".gaia-state"
$pidFile = Join-Path $stateDir "gaia-pid.json"

function Find-FreePort([int]$start) {
    $p = $start
    while (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) {
        $p++
    }
    return $p
}

function Get-ChildProcessIds([int]$parentId) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$parentId" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty ProcessId
}

function Stop-ProcessTree([int]$processId) {
    foreach ($child in Get-ChildProcessIds $processId) { Stop-ProcessTree $child }
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

function Stop-Gaia {
    $stoppedAny = $false
    $ports = @()

    if (Test-Path $pidFile) {
        $saved = Get-Content $pidFile -Raw | ConvertFrom-Json
        if ($saved.pid -and (Get-Process -Id $saved.pid -ErrorAction SilentlyContinue)) {
            Write-Host "==> Stopping GAIA (PID $($saved.pid))"
            Stop-ProcessTree $saved.pid
            $stoppedAny = $true
        }
        if ($saved.port) { $ports = @($saved.port) }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }

    if ($ports.Count -eq 0) { $ports = @($Port) }

    foreach ($listenPort in ($ports | Select-Object -Unique)) {
        Get-NetTCPConnection -LocalPort $listenPort -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Host "==> Stopping stray listener on port $listenPort (PID $($_.OwningProcess))"
                Stop-ProcessTree $_.OwningProcess
                $stoppedAny = $true
            }
    }

    Write-Host $(if ($stoppedAny) { "==> Stopped" } else { "==> Nothing was running" })
}

function Start-Gaia {
    if (-not $exePath) {
        Write-Error "GAIA executable not found next to this script, in dist\, or on PATH. Build it with scripts\build-release-windows.ps1, or place GAIA.exe next to this script."
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    $freePort = Find-FreePort $Port
    $log = Join-Path $stateDir "gaia.log"

    Write-Host "==> Starting GAIA ($exePath) on http://127.0.0.1:$freePort"
    $env:GAIA_PORT = "$freePort"
    $proc = Start-Process -FilePath $exePath `
        -PassThru -NoNewWindow -WorkingDirectory $exeDir `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"

    @{ pid = $proc.Id; port = $freePort } | ConvertTo-Json | Set-Content $pidFile
    Write-Host "==> GAIA: http://127.0.0.1:$freePort  (PID $($proc.Id), log: $log)"
}

switch ($Action) {
    "start" { Start-Gaia }
    "stop" { Stop-Gaia }
    "restart" { Stop-Gaia; Start-Sleep -Seconds 1; Start-Gaia }
}
