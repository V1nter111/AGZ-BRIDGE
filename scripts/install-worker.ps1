<#
.SYNOPSIS
One-command automated installer and configurer for AGZ Bridge Worker & Agent Zero.

.DESCRIPTION
Pairs with the AGZ Bridge Host on MAIN PC, installs/configures Agent Zero,
sets up Antigravity 2.0 CLI as the primary remote intelligence model,
enables worker execution for all tools, and performs end-to-end verification.

.PARAMETER HostUrl
URL of the AGZ Bridge Host on MAIN PC (e.g., http://192.168.31.136:8765 or Tailscale IP).

.PARAMETER PairingCode
One-time pairing code generated on the Host (e.g., AGZ-XXXX-YYYY-ZZZZ).

.PARAMETER WorkerName
Optional name to identify this worker PC. Defaults to the computer name.

.PARAMETER Port
Port on which Agent Zero Web UI will run. Defaults to 5080.

.PARAMETER InstallMode
Installation mode: "auto" (default), "docker", or "native".
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$HostUrl,

    [Parameter(Mandatory = $true)]
    [string]$PairingCode,

    [string]$WorkerName = $env:COMPUTERNAME,
    [int]$Port = 5080,
    [string]$InstallMode = "auto",
    [switch]$SkipTest,
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "             AGZ BRIDGE WORKER INSTALLER                  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$stateDir = Join-Path $env:USERPROFILE ".agz_worker"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$logFile = Join-Path $stateDir "installer.log"

function Log-Msg([string]$msg, [string]$color = "White") {
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $logEntry = "[$timestamp] $msg"
    Add-Content -Path $logFile -Value $logEntry -Encoding utf8
    Write-Host $msg -ForegroundColor $color
}

Log-Msg "Starting AGZ Bridge Worker Setup on $WorkerName..." "Cyan"
Log-Msg "Target Host: $HostUrl" "Gray"

# --- STEP 1: SYSTEM PREREQUISITES CHECK ---
Log-Msg "`n[1/7] Validating system requirements..." "Yellow"

# Check Windows Version
$os = Get-CimInstance Win32_OperatingSystem
Log-Msg "  Operating System: $($os.Caption) (Build $($os.BuildNumber))" "Gray"
if ([int]$os.BuildNumber -lt 17763) {
    throw "Windows 10 Build 17763 or higher is required."
}

# Check Architecture
$arch = $env:PROCESSOR_ARCHITECTURE
Log-Msg "  Architecture: $arch" "Gray"
if ($arch -notin @("AMD64", "ARM64")) {
    throw "Unsupported architecture: $arch. x64 or ARM64 is required."
}

# Check Disk Space (Require at least 4 GB)
$drive = Get-PSDrive -Name $env:SystemDrive[0]
$freeGb = [math]::Round($drive.Free / 1GB, 2)
Log-Msg "  Free Disk Space: $freeGb GB" "Gray"
if ($freeGb -lt 4.0) {
    throw "Insufficient disk space: at least 4 GB free is required (found $freeGb GB)."
}
Log-Msg "  System prerequisites PASSED." "Green"

# --- STEP 2: PAIR WITH MAIN PC HOST ---
Log-Msg "`n[2/7] Connecting to AGZ Bridge Host on MAIN PC..." "Yellow"

$cleanHostUrl = $HostUrl.TrimEnd("/")
try {
    $probe = Invoke-RestMethod -Uri "$cleanHostUrl/api/pair/status" -TimeoutSec 5 -ErrorAction Stop
    Log-Msg "  Host responded: $($probe.service) ($($probe.status))" "Green"
} catch {
    throw "Cannot connect to AGZ Bridge Host at $cleanHostUrl. Ensure the Host is running on MAIN PC and reachable over LAN/Tailscale: $_"
}

Log-Msg "  Pairing device using code '$PairingCode'..." "Yellow"
$pairPayload = @{
    pairing_code = $PairingCode.Trim()
    worker_name = $WorkerName
    os_info = "$($os.Caption) $arch"
} | ConvertTo-Json

try {
    $pairRes = Invoke-RestMethod -Uri "$cleanHostUrl/api/pair" -Method Post -Body $pairPayload -ContentType "application/json" -TimeoutSec 10 -ErrorAction Stop
} catch {
    $errDetail = $_
    try {
        if ($_.Exception.Response) {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $errDetail = $reader.ReadToEnd()
        }
    } catch {}
    throw "Pairing failed: $errDetail"
}

$workerToken = $pairRes.token
$defaultModel = $pairRes.default_model
Log-Msg "  Pairing SUCCESSFUL! Assigned token for $WorkerName." "Green"
Log-Msg "  Primary Intelligence Model: $defaultModel" "Cyan"

# Save paired worker state locally
$workerConfig = @{
    host_url = $cleanHostUrl
    token = $workerToken
    default_model = $defaultModel
    worker_name = $WorkerName
    installed_at = (Get-Date).ToString("o")
}
Set-Content -Path (Join-Path $stateDir "config.json") -Value ($workerConfig | ConvertTo-Json -Indent 2)

# --- STEP 3: PREPARE RUNTIME & AGENT ZERO DIRECTORIES ---
Log-Msg "`n[3/7] Setting up Agent Zero environment..." "Yellow"

$a0Root = Join-Path $env:USERPROFILE "agent-zero"
$instanceDir = Join-Path $a0Root "agent-zero"
$usrDir = Join-Path $instanceDir "usr"
$pluginsDir = Join-Path $usrDir "plugins\_model_config"
New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null

# Backup existing configuration if present
$presetsFile = Join-Path $pluginsDir "presets.yaml"
if (Test-Path $presetsFile) {
    $backupDir = Join-Path $usrDir ".backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Copy-Item $presetsFile -Destination $backupDir -Force
    Log-Msg "  Existing configuration backed up to $backupDir" "Gray"
}

# --- STEP 4: CONFIGURE AGZ BRIDGE AS PRIMARY MODEL ---
Log-Msg "`n[4/7] Configuring AGZ Bridge remote model preset in Agent Zero..." "Yellow"

$presetContent = @"
- name: Default
  chat:
    provider: other
    name: $defaultModel
    api_base: "$cleanHostUrl/v1"
    ctx_length: 1000000
    ctx_history: 0.7
    vision: true
    max_embeds: 10
    kwargs: {}
  utility:
    provider: other
    name: $defaultModel
    api_base: "$cleanHostUrl/v1"
    ctx_length: 128000
    ctx_input: 0.7
    kwargs: {}
  embedding:
    provider: huggingface
    name: sentence-transformers/all-MiniLM-L6-v2
    kwargs: {}
"@

Set-Content -Path $presetsFile -Value $presetContent -Encoding utf8
Log-Msg "  Saved presets.yaml -> Default preset configured to use $defaultModel via $cleanHostUrl/v1" "Green"

# Configure .env with Worker API token for 'other' provider
$envFile = Join-Path $usrDir ".env"
$envLines = @()
if (Test-Path $envFile) {
    $envLines = Get-Content $envFile | Where-Object { $_ -notmatch "^API_KEY_OTHER=" -and $_ -notmatch "^A0_SET_CHAT_MODEL=" }
}
$envLines += "API_KEY_OTHER=$workerToken"
$envLines += "A0_SET_CHAT_MODEL=$defaultModel"
Set-Content -Path $envFile -Value ($envLines -join "`n") -Encoding utf8
Log-Msg "  Saved worker token in Agent Zero environment." "Green"

# --- STEP 5: DEPLOY OR START AGENT ZERO ---
Log-Msg "`n[5/7] Deploying and starting Agent Zero container/service..." "Yellow"

$hasDocker = $false
try {
    $dockerCheck = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $hasDocker = $true
    }
} catch {}

if ($InstallMode -eq "docker" -or ($InstallMode -eq "auto" -and $hasDocker)) {
    Log-Msg "  Docker runtime detected. Launching Agent Zero container..." "Yellow"
    # Stop existing container if running
    docker rm -f agent-zero 2>$null | Out-Null
    
    # Run Agent Zero container with mapped usr directory
    $dockerCmd = "docker run -d --name agent-zero -p ${Port}:80 -v `"${usrDir}:/a0/usr`" --restart unless-stopped agent0ai/agent-zero"
    Log-Msg "  Executing: $dockerCmd" "Gray"
    $cid = Invoke-Expression $dockerCmd
    Log-Msg "  Container started successfully (ID: $($cid.Substring(0, 12)))." "Green"
} else {
    Log-Msg "  Docker not running. Setting up Agent Zero in native Python mode..." "Yellow"
    # Check Python and Git
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Log-Msg "  Installing Git via winget..." "Yellow"
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }

    $repoDir = Join-Path $instanceDir "app"
    if (-not (Test-Path $repoDir)) {
        Log-Msg "  Cloning Agent Zero repository..." "Yellow"
        git clone --depth 1 https://github.com/agent0ai/agent-zero.git $repoDir
    }

    # Setup Python venv
    $venvDir = Join-Path $instanceDir "venv"
    if (-not (Test-Path $venvDir)) {
        Log-Msg "  Creating Python virtual environment..." "Yellow"
        python -m venv $venvDir
    }
    $pyVenv = Join-Path $venvDir "Scripts\python.exe"
    & $pyVenv -m pip install --upgrade pip --quiet
    & $pyVenv -m pip install -r (Join-Path $repoDir "requirements.txt") --quiet

    # Start Native Service in Background
    $runScript = Join-Path $instanceDir "run_native.ps1"
    $runContent = @"
`$env:A0_DATA_DIR = "$usrDir"
Set-Location "$repoDir"
& "$pyVenv" main.py
"@
    Set-Content -Path $runScript -Value $runContent -Encoding utf8
    Start-Process -FilePath "powershell.exe" -ArgumentList "-WindowStyle Hidden -File `"$runScript`""
    Log-Msg "  Native Agent Zero process launched in background." "Green"
}

# --- STEP 6: CONFIGURE AUTO-START ---
Log-Msg "`n[6/7] Setting up automatic startup on Windows boot..." "Yellow"
$startupDir = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDir "AgentZero-Worker.lnk"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
if ($hasDocker) {
    $shortcut.TargetPath = "docker.exe"
    $shortcut.Arguments = "start agent-zero"
} else {
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-WindowStyle Hidden -File `"$instanceDir\run_native.ps1`""
}
$shortcut.Description = "Agent Zero Worker Auto-Start"
$shortcut.Save()
Log-Msg "  Startup shortcut created: $shortcutPath" "Green"

# --- STEP 7: VERIFICATION & INTEGRATION TEST ---
Log-Msg "`n[7/7] Performing end-to-end communication check..." "Yellow"

# Test 1: Verify token against Host /v1/models
try {
    $modelsCheck = Invoke-RestMethod -Uri "$cleanHostUrl/v1/models" `
        -Headers @{ Authorization = "Bearer $workerToken" } `
        -TimeoutSec 10 -ErrorAction Stop
    $modelList = ($modelsCheck.data | ForEach-Object { $_.id }) -join ", "
    Log-Msg "  TEST 1 PASSED: Models accessible via Host ($modelList)" "Green"
} catch {
    throw "TEST 1 FAILED: Could not access /v1/models using worker token: $_"
}

# Test 2: Send a lightweight prompt to Host /v1/chat/completions
if (-not $SkipTest) {
    Log-Msg "  Sending test completion prompt to Host..." "Yellow"
    $testPrompt = @{
        model = $defaultModel
        messages = @(
            @{ role = "user"; content = "Respond with 'AGZ WORKER VERIFICATION OK' to confirm connection." }
        )
    } | ConvertTo-Json

    try {
        $chatCheck = Invoke-RestMethod -Uri "$cleanHostUrl/v1/chat/completions" `
            -Method Post `
            -Headers @{ Authorization = "Bearer $workerToken" } `
            -Body $testPrompt `
            -ContentType "application/json" `
            -TimeoutSec 30 -ErrorAction Stop

        $ans = $chatCheck.choices[0].message.content
        Log-Msg "  TEST 2 PASSED: Host returned response: $($ans.Trim())" "Green"
        Log-Msg "  Reported Tokens: $($chatCheck.usage.total_tokens) (In: $($chatCheck.usage.prompt_tokens), Out: $($chatCheck.usage.completion_tokens))" "Gray"
    } catch {
        Log-Msg "  Warning on TEST 2: $($_)" "Yellow"
    }
}

Log-Msg "`n==========================================================" "Green"
Log-Msg "          AGZ BRIDGE WORKER SETUP COMPLETE!               " "Green"
Log-Msg "==========================================================" "Green"
Log-Msg "Agent Zero Web UI:     http://localhost:$Port" "Cyan"
Log-Msg "Remote Intelligence:   $defaultModel (via MAIN PC Antigravity)" "Cyan"
Log-Msg "Host Connection:       $cleanHostUrl" "Cyan"
Log-Msg "Tool Execution:        Strictly local on this WORKER PC" "Green"
Log-Msg "`nYou can now open http://localhost:$Port in your browser and start working!" "White"
