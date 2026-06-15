$ErrorActionPreference = "Stop"

$appName = "Amortization Calculator"
$installRoot = Join-Path $env:LOCALAPPDATA "AmortizationCalculator"
$appDir = Join-Path $installRoot "app"
$launcherPath = Join-Path $installRoot "run_amortization_app.ps1"
$launcherVbsPath = Join-Path $installRoot "launch_amortization_app.vbs"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$sourceAppDir = Join-Path $PSScriptRoot "app"
$minimumPythonVersion = [Version]"3.10.0"

function Find-Python {
    $pythonCommands = @(
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )

    foreach ($candidate in $pythonCommands) {
        $found = Get-Command $candidate["Exe"] -ErrorAction SilentlyContinue
        if ($found) {
            try {
                $versionText = & $candidate["Exe"] @($candidate["Args"] + @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"))
                $version = [Version]$versionText
            }
            catch {
                continue
            }

            if ($version -ge $minimumPythonVersion) {
                return $candidate
            }
        }
    }

    return $null
}

function Invoke-Python {
    param(
        [hashtable]$Python,
        [string[]]$Arguments
    )

    & $Python["Exe"] @($Python["Args"] + $Arguments)
}

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Prompt-For-PythonInstall {
    Write-Host ""
    Write-Host "Python 3.10 or newer was not found on this computer."
    Write-Host "This app needs Python before it can install Streamlit, pandas, and Plotly."
    Write-Host ""

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        $answer = Read-Host "Install Python 3.12 now using Windows Package Manager? (Y/N)"
        if ($answer -match "^[Yy]") {
            Write-Host ""
            Write-Host "Installing Python 3.12. This may take a few minutes..."
            winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                throw "Python install through winget failed with exit code $LASTEXITCODE."
            }
            Refresh-Path
            return
        }
    }
    else {
        Write-Host "Windows Package Manager (winget) was not found."
    }

    Write-Host ""
    Write-Host "Please install Python 3.10 or newer from:"
    Write-Host "https://www.python.org/downloads/"
    Write-Host ""
    Write-Host "During Python setup, check: Add Python to PATH"
    Write-Host "Then run this installer again."
    Write-Host ""
    throw "Python is required before installation can continue."
}

try {
    if (-not (Test-Path -LiteralPath $sourceAppDir)) {
        throw "Could not find bundled app folder: $sourceAppDir"
    }

    $python = Find-Python
    if (-not $python) {
        Prompt-For-PythonInstall
        $python = Find-Python
    }

    if (-not $python) {
        throw "Python still was not found. Restart this installer after Python finishes installing."
    }

    Write-Host ""
    Write-Host "Using Python command: $($python["Exe"]) $($python["Args"] -join ' ')"

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $appDir | Out-Null

    $settingsPath = Join-Path $appDir "settings.json"
    $settingsBackupPath = Join-Path $installRoot "settings.json.backup"

    if (Test-Path -LiteralPath $settingsPath) {
        Copy-Item -LiteralPath $settingsPath -Destination $settingsBackupPath -Force
    }

    Get-ChildItem -LiteralPath $sourceAppDir -Force |
        Where-Object { $_.Name -ne "settings.json" } |
        Copy-Item -Destination $appDir -Recurse -Force

    if ((-not (Test-Path -LiteralPath $settingsPath)) -and
        (Test-Path -LiteralPath $settingsBackupPath)) {
        Copy-Item -LiteralPath $settingsBackupPath -Destination $settingsPath -Force
    }

    $venvDir = Join-Path $installRoot ".venv"
    if (-not (Test-Path -LiteralPath $venvDir)) {
        Invoke-Python -Python $python -Arguments @("-m", "venv", $venvDir)
    }

    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Could not create Python virtual environment."
    }

    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $appDir "requirements.txt")

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "run_amortization_app.ps1") -Destination $launcherPath -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "launch_amortization_app.vbs") -Destination $launcherVbsPath -Force

    $launcherExePath = Join-Path $appDir "Amortization Calculator.exe"
    if (Test-Path -LiteralPath $launcherExePath) {
        $shortcutTarget = $launcherExePath
        $shortcutArgs = ""
        $shortcutWorkingDirectory = $appDir
    }
    else {
        $shortcutTarget = "wscript.exe"
        $shortcutArgs = "//B //Nologo `"$launcherVbsPath`""
        $shortcutWorkingDirectory = $installRoot
    }
    $iconPath = Join-Path $appDir "app_icon.ico"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($desktopShortcut)
    $shortcut.TargetPath = $shortcutTarget
    $shortcut.Arguments = $shortcutArgs
    $shortcut.WorkingDirectory = $shortcutWorkingDirectory
    if (Test-Path -LiteralPath $iconPath) {
        $shortcut.IconLocation = $iconPath
    }
    else {
        $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
    }
    $shortcut.Save()

    Write-Host ""
    Write-Host "$appName installed successfully."
    Write-Host "Use the Desktop shortcut named '$appName' to start the app."
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Host "Installation did not complete."
    Write-Host $_.Exception.Message
    Write-Host ""
    exit 1
}
