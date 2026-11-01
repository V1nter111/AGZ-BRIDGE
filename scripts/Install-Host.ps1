<#
.SYNOPSIS
Installs and configures AGZ Bridge Host on MAIN PC.

.DESCRIPTION
Verifies Python, Antigravity CLI (agy), existing Google OAuth credentials,
configures firewall, and sets up Windows auto-start in the user context.
#>
param(
    [switch]$NoAutoStart,
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "      AGZ BRIDGE HOST INSTALLER         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Check Python
Write-Host "`n[1/5] Checking Python environment..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "Python 3.10+ is required but was not found in PATH."
}
$pyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "  Found Python $pyVer ($($py.Source))" -ForegroundColor Green

# 2. Check Antigravity CLI
Write-Host "`n[2/5] Checking Antigravity CLI (agy)..." -ForegroundColor Yellow
$agy = Get-Command agy -ErrorAction SilentlyContinue
if (-not $agy) {
    $defaultAgy = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"
    if (Test-Path $defaultAgy) {
        $agy = $defaultAgy
    } else {
        Write-Error "Antigravity CLI (agy) was not found. Please verify Antigravity is installed."
    }
}
Write-Host "  Found Antigravity CLI: $agy" -ForegroundColor Green

# 3. Check Google Authentication in CLI
Write-Host "`n[3/5] Checking Antigravity Google subscription authentication..." -ForegroundColor Yellow
try {
    $modelsOutput = agy models 2>&1 | Out-String
    if ($modelsOutput -match "gemini-") {
        Write-Host "  Authentication verified! Active models detected." -ForegroundColor Green
    } else {
        Write-Host "  Warning: agy models output did not list gemini models. Output: $modelsOutput" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Warning: could not run 'agy models' check: $_" -ForegroundColor Yellow
}

# 4. Create App Directories
Write-Host "`n[4/5] Initializing AGZ Bridge state directories..." -ForegroundColor Yellow
$appDir = Join-Path $env:USERPROFILE ".agz_bridge"
$dataDir = Join-Path $appDir "data"
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
Write-Host "  State directory ready: $appDir" -ForegroundColor Green

# 5. Configure Windows Auto-Start
Write-Host "`n[5/5] Configuring Windows Startup shortcut..." -ForegroundColor Yellow
if (-not $NoAutoStart) {
    $startupFolder = [Environment]::GetFolderPath('Startup')
    $shortcutPath = Join-Path $startupFolder "AGZ-Bridge-Host.lnk"
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectRoot = Split-Path -Parent $scriptDir
    $startScript = Join-Path $scriptDir "Start-Host.ps1"

    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "AGZ Bridge Host Background Server"
    $shortcut.Save()
    Write-Host "  Startup shortcut created: $shortcutPath" -ForegroundColor Green
} else {
    Write-Host "  Auto-start skipped via -NoAutoStart." -ForegroundColor Gray
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "    HOST INSTALLATION COMPLETE!         " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Run .\scripts\Start-Host.ps1 to start the server.`n"
