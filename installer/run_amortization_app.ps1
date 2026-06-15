$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "AmortizationCalculator"
$appDir = Join-Path $installRoot "app"
$venvPython = Join-Path $installRoot ".venv\Scripts\python.exe"
$appFile = Join-Path $appDir "app.py"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "The app is not installed correctly. Run install.ps1 again."
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path -LiteralPath $appFile)) {
    Write-Host "Could not find app.py. Run install.ps1 again."
    Read-Host "Press Enter to exit"
    exit 1
}

Set-Location $appDir
& $venvPython -m streamlit run $appFile
