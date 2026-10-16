[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFlutter
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$backendEnv = Join-Path $projectRoot "backend\.env"
$backendEnvExample = Join-Path $projectRoot "backend\.env.example"

Set-Location -LiteralPath $projectRoot

if (-not $SkipBackend) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python 3.12 is required but 'python' was not found on PATH."
    }

    $pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.12") {
        throw "Python 3.12 is required. Detected: $pythonVersion"
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host "Creating Python virtual environment..."
        python -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }
    }

    Write-Host "Installing backend dependencies..."
    & $venvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "Failed to update Python packaging tools." }
    & $venvPython -m pip install -r (Join-Path $projectRoot "backend\requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install backend dependencies." }

    if (-not (Test-Path -LiteralPath $backendEnv)) {
        Copy-Item -LiteralPath $backendEnvExample -Destination $backendEnv
        Write-Host "Created backend\.env from the example."
    }
}

if (-not $SkipFlutter) {
    if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
        throw "Flutter is required but 'flutter' was not found on PATH."
    }

    Write-Host "Installing Flutter dependencies..."
    Push-Location -LiteralPath (Join-Path $projectRoot "app_flutter")
    try {
        flutter pub get
        if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed." }
    } finally {
        Pop-Location
    }
}

Write-Host "Setup complete."
Write-Host "Backend: .\scripts\start_backend.ps1"
Write-Host "Flutter: .\scripts\start_flutter.ps1"
