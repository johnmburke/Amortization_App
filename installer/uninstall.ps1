$ErrorActionPreference = "Stop"

$appName = "Amortization Calculator"
$installRoot = Join-Path $env:LOCALAPPDATA "AmortizationCalculator"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"

if (Test-Path -LiteralPath $desktopShortcut) {
    Remove-Item -LiteralPath $desktopShortcut -Force
}

if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}

Write-Host ""
Write-Host "$appName removed successfully."
Write-Host ""
Read-Host "Press Enter to exit"
