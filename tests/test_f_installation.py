"""TEST F: Installation scripts structure, syntax, and parameter verification."""
from pathlib import Path
import subprocess
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def test_f1_all_scripts_exist():
    """Verify all required scripts exist."""
    expected = [
        "Install-Host.ps1",
        "Start-Host.ps1",
        "Stop-Host.ps1",
        "Restart-Host.ps1",
        "Get-HostStatus.ps1",
        "Update-Host.ps1",
        "install-worker.ps1",
    ]
    for name in expected:
        p = SCRIPTS_DIR / name
        assert p.exists(), f"Missing required script: {name}"


def test_f2_powershell_syntax():
    """Validate syntax of all PowerShell scripts using PowerShell parser."""
    for script_path in SCRIPTS_DIR.glob("*.ps1"):
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$errors); if ($errors.Count -gt 0) {{ Write-Error ($errors | Out-String); exit 1 }} else {{ exit 0 }}"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Syntax error in {script_path.name}: {res.stderr}"
