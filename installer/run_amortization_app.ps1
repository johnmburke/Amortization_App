$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "AmortizationCalculator"
$appDir = Join-Path $installRoot "app"
$venvPython = Join-Path $installRoot ".venv\Scripts\python.exe"
$venvPythonw = Join-Path $installRoot ".venv\Scripts\pythonw.exe"
$launcherFile = Join-Path $appDir "desktop_launcher.py"

if (-not (Test-Path -LiteralPath $launcherFile)) {
    exit 1
}

if (Test-Path -LiteralPath $venvPythonw) {
    $pythonLauncher = $venvPythonw
}
elseif (Test-Path -LiteralPath $venvPython) {
    $pythonLauncher = $venvPython
}
else {
    exit 1
}

Start-Process `
    -FilePath $pythonLauncher `
    -ArgumentList @($launcherFile) `
    -WorkingDirectory $appDir `
    -WindowStyle Hidden
