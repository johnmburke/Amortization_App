$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "AmortizationCalculator"
$appDir = Join-Path $installRoot "app"
$venvPython = Join-Path $installRoot ".venv\Scripts\python.exe"
$appFile = Join-Path $appDir "app.py"
$appPort = 8501
$appUrl = "http://localhost:$appPort"

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

function Get-AppBrowserConnectionCount {
    param([int]$Port)

    try {
        $connections = Get-NetTCPConnection `
            -LocalPort $Port `
            -State Established `
            -ErrorAction SilentlyContinue

        if ($connections) {
            return @($connections).Count
        }
    }
    catch {
        return 0
    }

    return 0
}

function Wait-ForBrowserDisconnect {
    param([int]$Port)

    $sawBrowserConnection = $false
    $emptyChecks = 0

    while ($true) {
        $connectionCount = Get-AppBrowserConnectionCount -Port $Port

        if ($connectionCount -gt 0) {
            $sawBrowserConnection = $true
            $emptyChecks = 0
        }
        elseif ($sawBrowserConnection) {
            $emptyChecks += 1
            if ($emptyChecks -ge 8) {
                return
            }
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
    Start-Process $appUrl
    Wait-ForBrowserDisconnect -Port $appPort
}
finally {
    if ($streamlitProcess -and -not $streamlitProcess.HasExited) {
        Stop-Process -Id $streamlitProcess.Id -Force
    }
}
