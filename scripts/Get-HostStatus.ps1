<#
.SYNOPSIS
Retrieves and displays real-time status of AGZ Bridge Host.
#>
param(
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$hostBase = "http://localhost:$Port"

try {
    $health = Invoke-RestMethod -Uri "$hostBase/health" -TimeoutSec 3 -ErrorAction Stop
} catch {
    Write-Host "AGZ Bridge Host is NOT running (cannot connect to $hostBase)." -ForegroundColor Red
    return
}

$status = Invoke-RestMethod -Uri "$hostBase/api/pair/status"
$pairData = Invoke-RestMethod -Uri "$hostBase/api/pair/generate" -Method Post
$metrics = Invoke-RestMethod -Uri "$hostBase/api/metrics"
$workers = Invoke-RestMethod -Uri "$hostBase/api/pair/workers"

$primaryUrl = if ($status.tailscale_ip) { "http://$($status.tailscale_ip):$Port" } else { "http://$($status.lan_ip):$Port" }
$activeCode = $pairData.pairing_code

Write-Host "Service:          AGZ Bridge Host" -ForegroundColor Cyan
Write-Host "LAN Address:      http://$($status.lan_ip):$Port" -ForegroundColor White
if ($status.tailscale_ip) {
    Write-Host "Tailscale:        http://$($status.tailscale_ip):$Port" -ForegroundColor White
}
Write-Host "Web Dashboard:    http://localhost:$Port/dashboard" -ForegroundColor Green
Write-Host "Default Model:    $($status.default_model)" -ForegroundColor Yellow
Write-Host "Total Requests:   $($metrics.total_requests) ($($metrics.successful_requests) OK / $($metrics.failed_requests) ERR)" -ForegroundColor Gray
Write-Host "Total Tokens:     $($metrics.total_tokens)" -ForegroundColor Gray
Write-Host "Paired Workers:   $($workers.Count)" -ForegroundColor Gray

Write-Host "`n--------------------------------------------------------" -ForegroundColor Cyan
Write-Host " ACTIVE PAIRING CODE (Valid 15m): $activeCode" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan

$rawUrl = "https://raw.githubusercontent.com/V1nter111/AGZ-BRIDGE/v1.0.0/scripts/install-worker.ps1"
$workerCmd = "& ([scriptblock]::Create((irm `"$rawUrl`"))) -HostUrl `"$primaryUrl`" -PairingCode `"$activeCode`""

Write-Host "`nONE COMMAND FOR WORKER PC (PowerShell):" -ForegroundColor Cyan
Write-Host $workerCmd -ForegroundColor Green
Write-Host ""
