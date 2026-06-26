# Build a standalone Windows app folder for ARIA with PyInstaller.
# Run from the project root:  .\build.ps1
# Output: dist\ARIA\ARIA.exe

$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "venv not found at $py. Create it and install requirements first."
    exit 1
}

& $py -m pip install pyinstaller --quiet
& $py -m PyInstaller (Join-Path $PSScriptRoot "aria.spec") --noconfirm --clean

Write-Host ""
Write-Host "Build complete. Launch: dist\ARIA\ARIA.exe" -ForegroundColor Green
Write-Host "Note: copy your .env next to ARIA.exe (or set env vars) before first run." -ForegroundColor Yellow
