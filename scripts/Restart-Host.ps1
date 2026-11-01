<#
.SYNOPSIS
Restarts the AGZ Bridge Host server.
#>
param(
    [int]$Port = 8765
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir "Stop-Host.ps1")
Start-Sleep -Seconds 1
& (Join-Path $scriptDir "Start-Host.ps1") -Port $Port
