<#
.SYNOPSIS
Stops the AGZ Bridge Host server.
#>
$ErrorActionPreference = 'SilentlyContinue'
$pidFile = Join-Path $env:USERPROFILE ".agz_bridge\host.pid"

if (Test-Path $pidFile) {
    $procId = Get-Content $pidFile
    if ($procId) {
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($p) {
            Write-Host "Stopping AGZ Bridge Host process PID $procId..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
            Start-Sleep -Seconds 1
        }
    }
    Remove-Item $pidFile -Force
}

# Also cleanup any stray processes on port 8765
$netstat = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
if ($netstat) {
    foreach ($conn in $netstat) {
        if ($conn.OwningProcess -gt 0) {
            Write-Host "Terminating listening process on port 8765 (PID $($conn.OwningProcess))..." -ForegroundColor Yellow
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "AGZ Bridge Host is stopped." -ForegroundColor Green
