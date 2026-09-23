# xaloAC installer — adds this folder to user PATH permanently
$ErrorActionPreference = "Stop"
$ToolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolDir = (Resolve-Path $ToolDir).Path

Write-Host "[*] xaloAC install" -ForegroundColor Cyan
Write-Host "    dir: $ToolDir"

# Verify files
$main = Join-Path $ToolDir "xaloAC.py"
$cmd  = Join-Path $ToolDir "xaloAC.cmd"
if (-not (Test-Path $main)) { throw "xaloAC.py missing" }
if (-not (Test-Path $cmd))  { throw "xaloAC.cmd missing" }

# User PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$parts = $userPath -split ";" | Where-Object { $_ -and $_.Trim() -ne "" }

if ($parts -contains $ToolDir) {
    Write-Host "[+] Already on user PATH" -ForegroundColor Green
} else {
    $newPath = ($parts + $ToolDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "[+] Added to user PATH: $ToolDir" -ForegroundColor Green
}

# Current session
if ($env:Path -notlike "*$ToolDir*") {
    $env:Path = "$ToolDir;$env:Path"
    Write-Host "[+] Added to current session PATH" -ForegroundColor Green
}

# Smoke test
Write-Host "[*] Smoke test..." -ForegroundColor Cyan
& py -3 $main --version
Write-Host "[+] Install complete. Open a NEW terminal and type: xaloAC" -ForegroundColor Green
Write-Host "    Or in this session: xaloAC stats" -ForegroundColor Gray
