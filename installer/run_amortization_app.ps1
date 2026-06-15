$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "AmortizationCalculator"
$appDir = Join-Path $installRoot "app"
$venvPython = Join-Path $installRoot ".venv\Scripts\python.exe"
$appFile = Join-Path $appDir "app.py"
$appPort = 8501
$appUrl = "http://localhost:$appPort"
$browserProfile = Join-Path $installRoot "browser_profile"

function Find-AppBrowser {
    $browserPaths = @(
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe")
    )

    foreach ($browserPath in $browserPaths) {
        if (Test-Path -LiteralPath $browserPath) {
            return $browserPath
        }
    }

    return $null
}

function Wait-ForApp {
    param([string]$Url)

    for ($attempt = 1; $attempt -le 40; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1 | Out-Null
            return $true
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }

    return $false
}

function Wait-ForBrowserProfileExit {
    param([string]$ProfilePath)

    Start-Sleep -Seconds 1

    while ($true) {
        $browserProcesses = Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.Contains($ProfilePath)
            }

        if (-not $browserProcesses) {
            return
        }

        Start-Sleep -Seconds 1
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    exit 1
}

if (-not (Test-Path -LiteralPath $appFile)) {
    exit 1
}

New-Item -ItemType Directory -Force -Path $browserProfile | Out-Null

$streamlitArgs = @(
    "-m",
    "streamlit",
    "run",
    $appFile,
    "--server.port=$appPort",
    "--server.headless=true",
    "--browser.gatherUsageStats=false"
)

$streamlitProcess = Start-Process `
    -FilePath $venvPython `
    -ArgumentList $streamlitArgs `
    -WorkingDirectory $appDir `
    -WindowStyle Hidden `
    -PassThru

try {
    Wait-ForApp -Url $appUrl | Out-Null

    $browserPath = Find-AppBrowser
    if ($browserPath) {
        $browserProcess = Start-Process `
            -FilePath $browserPath `
            -ArgumentList @(
                "--app=$appUrl",
                "--user-data-dir=$browserProfile",
                "--no-first-run"
            ) `
            -PassThru

        Wait-ForBrowserProfileExit -ProfilePath $browserProfile
    }
    else {
        Start-Process $appUrl
        Wait-Process -Id $streamlitProcess.Id
    }
}
finally {
    if ($streamlitProcess -and -not $streamlitProcess.HasExited) {
        Stop-Process -Id $streamlitProcess.Id -Force
    }
}
