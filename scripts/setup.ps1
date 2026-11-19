[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFlutter,
    [switch]$SkipToolchainCheck
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$backendEnv = Join-Path $projectRoot "backend\.env"
$backendEnvExample = Join-Path $projectRoot "backend\.env.example"

Set-Location -LiteralPath $projectRoot

function Get-Python312Command {
    $candidates = @()

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $candidates += [pscustomobject]@{
            Executable = $pyLauncher.Source
            PrefixArguments = @("-3.12")
            DisplayName = "py -3.12"
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $candidates += [pscustomobject]@{
            Executable = $python.Source
            PrefixArguments = @()
            DisplayName = "python"
        }
    }

    foreach ($candidate in $candidates) {
        $arguments = @($candidate.PrefixArguments) + @(
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        )
        $version = & $candidate.Executable @arguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -eq "3.12") {
            return $candidate
        }
    }

    throw "Python 3.12 was not found. Install 64-bit Python 3.12 and enable the Python launcher or add Python to PATH."
}

function Invoke-PythonCommand {
    param(
        [Parameter(Mandatory)]$PythonCommand,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $allArguments = @($PythonCommand.PrefixArguments) + $Arguments
    & $PythonCommand.Executable @allArguments
}

if (-not $SkipBackend) {
    $pythonCommand = Get-Python312Command
    Write-Host "Using Python 3.12 from $($pythonCommand.DisplayName)."

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host "Creating Python virtual environment..."
        Invoke-PythonCommand -PythonCommand $pythonCommand -Arguments @(
            "-m", "venv", $venvPath
        )
        if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }
    }

    Write-Host "Installing backend dependencies..."
    & $venvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "Failed to update Python packaging tools." }
    & $venvPython -m pip install -r (Join-Path $projectRoot "backend\requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install backend dependencies." }

    & $venvPython -c "import fastapi, uvicorn, cv2, numpy, onnxruntime; print('Backend dependencies verified.')"
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency verification failed." }

    if (-not (Test-Path -LiteralPath $backendEnv)) {
        Copy-Item -LiteralPath $backendEnvExample -Destination $backendEnv
        Write-Host "Created backend\.env from the example."
    }
}

if (-not $SkipFlutter) {
    if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
        throw "Flutter is required but 'flutter' was not found on PATH."
    }

    if (-not $SkipToolchainCheck) {
        Write-Host "Checking the Flutter Windows toolchain..."
        flutter config --enable-windows-desktop
        if ($LASTEXITCODE -ne 0) { throw "Could not enable Flutter Windows desktop support." }

        $doctorOutput = flutter doctor -v 2>&1
        $doctorText = $doctorOutput -join [Environment]::NewLine
        Write-Host $doctorText
        if ($doctorText -notmatch "Visual Studio - develop Windows apps") {
            throw "Flutter cannot find the Visual Studio Windows desktop toolchain. Install Visual Studio 2022 with Desktop development with C++."
        }
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
Write-Host "One-command Windows run: .\scripts\start_windows.ps1"
Write-Host "Two-terminal run: .\scripts\start_backend.ps1, then .\scripts\start_flutter.ps1"
Write-Host "Verify: .\scripts\verify_project.ps1"
