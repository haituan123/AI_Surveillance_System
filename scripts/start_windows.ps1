[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8000,
    [int]$StartupTimeoutSeconds = 60,
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$flutterRoot = Join-Path $projectRoot "app_flutter"
$backendUrl = "http://${BindAddress}:$Port"
$healthUrl = "$backendUrl/health/readiness"
$backendOutputLog = Join-Path $projectRoot "backend\backend_server.out.log"
$backendErrorLog = Join-Path $projectRoot "backend\backend_server.err.log"
$backendProcess = $null
$startedBackend = $false

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The local Python environment is missing. Run: .\scripts\setup.ps1"
}

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw "Flutter was not found on PATH. Run setup after installing Flutter."
}

function Get-BackendReadiness {
    try {
        return Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3
    } catch {
        return $null
    }
}

try {
    $readiness = Get-BackendReadiness
    if ($readiness -and $readiness.status -eq "ready") {
        Write-Host "Using the backend already running at $backendUrl."
    } else {
        Write-Host "Starting the local backend at $backendUrl..."
        $backendProcess = Start-Process `
            -FilePath $venvPython `
            -ArgumentList @(
                "-m", "uvicorn", "backend.main:app",
                "--host", $BindAddress,
                "--port", $Port.ToString()
            ) `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $backendOutputLog `
            -RedirectStandardError $backendErrorLog `
            -PassThru
        $startedBackend = $true

        $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
        do {
            Start-Sleep -Milliseconds 500
            if ($backendProcess.HasExited) {
                $errorTail = Get-Content -LiteralPath $backendErrorLog -Tail 20 -ErrorAction SilentlyContinue
                throw "The backend exited during startup.`n$errorTail"
            }
            $readiness = Get-BackendReadiness
        } while ((-not $readiness -or $readiness.status -ne "ready") -and (Get-Date) -lt $deadline)

        if (-not $readiness -or $readiness.status -ne "ready") {
            throw "The backend did not become ready within $StartupTimeoutSeconds seconds. Check backend\backend_server.err.log."
        }
        Write-Host "Local backend is ready."
    }

    if ($VerifyOnly) {
        Write-Host "Local Windows backend verification passed."
        return
    }

    Push-Location -LiteralPath $flutterRoot
    try {
        Write-Host "Starting the Flutter Windows application..."
        flutter run -d windows --dart-define="BACKEND_URL=$backendUrl"
        if ($LASTEXITCODE -ne 0) {
            throw "Flutter exited with code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($startedBackend -and $backendProcess -and -not $backendProcess.HasExited) {
        Write-Host "Stopping the local backend..."
        Stop-Process -Id $backendProcess.Id -Force
    }
}
