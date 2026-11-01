<#
.SYNOPSIS
Starts the AGZ Bridge Host server in background.
#>
param(
    [int]$Port = 8765,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pidFile = Join-Path $env:USERPROFILE ".agz_bridge\host.pid"
$logFile = Join-Path $env:USERPROFILE ".agz_bridge\host.log"

# Check if already running
if (Test-Path $pidFile) {
    $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        Write-Host "AGZ Bridge Host is already running with PID $existingPid." -ForegroundColor Yellow
        Write-Host "Checking status..." -ForegroundColor Gray
        & (Join-Path $scriptDir "Get-HostStatus.ps1")
        return
    }
}

Write-Host "Starting AGZ Bridge Host..." -ForegroundColor Cyan

$env:PYTHONPATH = $projectRoot
if ($Foreground) {
    python -m agz_bridge.main --port $Port
    return
}

# Start background process
$process = Start-Process -FilePath "python" -ArgumentList "-m agz_bridge.main --port $Port" `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError (Join-Path $env:USERPROFILE ".agz_bridge\host_err.log") `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $pidFile -Value $process.Id
Write-Host "Host process launched with PID $($process.Id)." -ForegroundColor Gray

# Wait for server to become healthy
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($res.status -eq "healthy") {
            $healthy = $true
            break
        }
    } catch {}
}

if (-not $healthy) {
    Write-Error "Host server failed to start within 15 seconds. Check log at $logFile"
}

# Query status and pairing code
Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "             AGZ BRIDGE HOST IS RUNNING!                " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

& (Join-Path $scriptDir "Get-HostStatus.ps1")
