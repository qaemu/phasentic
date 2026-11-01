# Phasentic installer for Windows. Run in PowerShell:
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/qaemu/phasentic/main/install.ps1 | iex"
# Installs uv (a Python installer, no admin rights needed), Python 3.12 and Phasentic,
# downloads the COD reference database (8.6 GB, about 10 GB free disk needed),
# adds Phasentic shortcuts to the Desktop and Start Menu, and starts it.

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# A running Phasentic locks its files and makes reinstalling fail.
$bin = uv tool dir --bin
$tools = uv tool dir
Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -like "$tools\phasentic\*" -or $_.CommandLine -like "*$bin\phasentic.exe*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Installing Phasentic..."
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/heads/main.zip
if ($LASTEXITCODE -ne 0) { throw "Phasentic could not be installed." }
uv tool update-shell | Out-Null

$phasentic = Join-Path $bin "phasentic.exe"
& $phasentic setup-cod
if ($LASTEXITCODE -ne 0) { throw "The reference database is not installed yet. Run this installer again to resume." }

Write-Host "Adding Phasentic shortcuts to the Desktop and Start Menu..."
$icon = Join-Path $env:USERPROFILE ".phasentic\phasentic.ico"
try { irm https://raw.githubusercontent.com/qaemu/phasentic/main/assets/phasentic.ico -OutFile $icon } catch { $icon = $null }
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $shortcut = $shell.CreateShortcut((Join-Path $folder "Phasentic.lnk"))
    $shortcut.TargetPath = $phasentic
    $shortcut.Arguments = "serve --open"
    $shortcut.WorkingDirectory = $env:USERPROFILE
    $shortcut.Description = "Start Phasentic and open it in the browser"
    if ($icon) { $shortcut.IconLocation = $icon }
    $shortcut.Save()
}

Write-Host ""
Write-Host "Phasentic is installed. Starting it now; next time, open the Phasentic shortcut."
Start-Process $phasentic -ArgumentList "serve", "--open"
