# Build the PyInstaller onedir bundle and wrap it in a one-click installer with
# Inno Setup. (Signing is done in CI with signtool; this local build is unsigned.)
# Run on Windows from the repo root:
#   $env:TEMPSENSOR_VERSION="2.4.0"; ./packaging/windows/build_installer.ps1
param(
  [string]$Version = $(if ($env:TEMPSENSOR_VERSION) { $env:TEMPSENSOR_VERSION } else { "0.0.0" })
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt pyinstaller -q
python packaging\gen_third_party_licenses.py
$env:TEMPSENSOR_VERSION = $Version
python -m PyInstaller --clean --noconfirm packaging\temperature_hub.spec
Copy-Item -Force LICENSE, THIRD-PARTY-LICENSES.md dist\temperature-hub\

# Compile the installer (Inno Setup's iscc must be on PATH — `choco install innosetup`).
iscc "/DAppVersion=$Version" "packaging\windows\setpoint.iss"

$setup = Get-ChildItem "dist\installer\Setpoint-Setup-*.exe" | Select-Object -First 1
Write-Host "[installer] Built $($setup.FullName)"
