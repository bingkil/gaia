#!/usr/bin/env pwsh
# Start, stop, or restart the GAIA backend + frontend dev servers.
#
# Usage:
#   scripts/dev.ps1 start   [-Port 8000] [-BackendOnly] [-FrontendOnly]
#   scripts/dev.ps1 stop
#   scripts/dev.ps1 restart [-Port 8000] [-BackendOnly] [-FrontendOnly]
#
# The backend port is auto-bumped past anything already listening, starting
# from -Port. The frontend always asks Vite for its own port (5173, bumped by
# Vite itself if that is taken) and is pointed at wherever the backend landed
# via GAIA_API. PIDs and the chosen ports are recorded in .dev/dev-pids.json
# so `stop`/`restart` can find and fully tear down both process trees, plus
# anything left listening on a previously used port.

param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart")]
    [string]$Action = "start",

    [int]$Port = 8000,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $root ".dev"
$pidFile = Join-Path $stateDir "dev-pids.json"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

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

# Post-order: kill children before the parent, so nothing gets a chance to
# respawn a sibling after we think we are done. `npm run dev` in particular
# fans out through cmd.exe into an npm shim into the real node/vite process.
function Stop-ProcessTree([int]$processId) {
    foreach ($child in Get-ChildProcessIds $processId) {
        Stop-ProcessTree $child
    }
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

function Stop-Dev {
    $stoppedAny = $false
    $ports = @()

    if (Test-Path $pidFile) {
        $saved = Get-Content $pidFile -Raw | ConvertFrom-Json
        foreach ($entry in @(
                @{ name = "backend"; id = $saved.backend },
                @{ name = "frontend"; id = $saved.frontend }
            )) {
            $procId = $entry.id
            if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
                Write-Host "==> Stopping $($entry.name) tree (PID $procId)"
                Stop-ProcessTree $procId
                $stoppedAny = $true
            }
        }
        $ports = @($saved.port, $saved.frontendPort) | Where-Object { $_ }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }

    if ($ports.Count -eq 0) { $ports = @(8000, 5173) }

    # Safety net: anything still bound to a known dev port, saved PID or not.
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

function Start-Dev {
    Set-Location $root
    $backendPid = $null
    $frontendPid = $null
    $frontendPort = $null
    $backendPort = if ($FrontendOnly) { $Port } else { Find-FreePort $Port }

    if (-not $FrontendOnly) {
        Write-Host "==> Starting backend on http://127.0.0.1:$backendPort"
        $backendLog = Join-Path $stateDir "backend.log"
        $backend = Start-Process -FilePath "uv" `
            -ArgumentList "run", "gaia", "serve", "--port", "$backendPort" `
            -PassThru -NoNewWindow -WorkingDirectory $root `
            -RedirectStandardOutput $backendLog -RedirectStandardError "$backendLog.err"
        $backendPid = $backend.Id
    }

    if (-not $BackendOnly) {
        Write-Host "==> Starting frontend (Vite picks its own port, bumping past 5173 if busy)"
        $frontendLog = Join-Path $stateDir "frontend.log"
        $env:GAIA_API = "http://127.0.0.1:$backendPort"
        $frontend = Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c", "npm", "run", "dev" `
            -PassThru -NoNewWindow -WorkingDirectory (Join-Path $root "web") `
            -RedirectStandardOutput $frontendLog -RedirectStandardError "$frontendLog.err"
        $frontendPid = $frontend.Id

        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-Path $frontendLog) {
                $match = Select-String -Path $frontendLog -Pattern "Local:\s+http://localhost:(\d+)" -ErrorAction SilentlyContinue
                if ($match) { $frontendPort = [int]$match.Matches[0].Groups[1].Value; break }
            }
        }
    }

    @{
        backend      = $backendPid
        frontend     = $frontendPid
        port         = $backendPort
        frontendPort = $frontendPort
    } | ConvertTo-Json | Set-Content $pidFile

    if ($backendPid) {
        Write-Host "==> Backend:  http://127.0.0.1:$backendPort  (PID $backendPid, log: $stateDir\backend.log)"
    }
    if ($frontendPid) {
        $url = if ($frontendPort) { "http://localhost:$frontendPort" } else { "check $stateDir\frontend.log" }
        Write-Host "==> Frontend: $url  (PID $frontendPid, log: $stateDir\frontend.log)"
    }
}

switch ($Action) {
    "start" { Start-Dev }
    "stop" { Stop-Dev }
    "restart" { Stop-Dev; Start-Sleep -Seconds 1; Start-Dev }
}
