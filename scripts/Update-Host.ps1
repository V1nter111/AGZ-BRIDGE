<#
.SYNOPSIS
Updates AGZ Bridge Host from Git and restarts server.
#>
param(
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Write-Host "Updating AGZ Bridge repository..." -ForegroundColor Cyan
Set-Location $projectRoot
git pull origin main

Write-Host "Restarting Host..." -ForegroundColor Cyan
& (Join-Path $scriptDir "Restart-Host.ps1") -Port $Port
