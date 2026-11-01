# Phasentic installer for Windows. Run in PowerShell:
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/qaemu/phasentic/main/install.ps1 | iex"
# Installs uv (a Python installer, no admin rights needed), Python 3.12 and Phasentic,
# then downloads the COD reference database (8.6 GB, about 10 GB free disk needed).

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Installing Phasentic..."
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/heads/main.zip
if ($LASTEXITCODE -ne 0) { throw "Phasentic could not be installed." }
uv tool update-shell | Out-Null

$phasentic = Join-Path (uv tool dir --bin) "phasentic.exe"
& $phasentic setup-cod
if ($LASTEXITCODE -ne 0) { throw "The reference database is not installed yet. Run this installer again to resume." }

Write-Host ""
Write-Host "Phasentic is installed. Open a new terminal and run: phasentic serve"
