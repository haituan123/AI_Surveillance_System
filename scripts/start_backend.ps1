param(
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonCommand = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
Set-Location -LiteralPath $projectRoot

& $pythonCommand -c "import fastapi, uvicorn, cv2; print('Backend dependencies OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Backend dependencies are missing. Run: .\scripts\setup.ps1"
}

$uvicornArguments = @(
    "-m", "uvicorn", "backend.main:app",
    "--host", $BindAddress,
    "--port", $Port.ToString()
)
if ($Reload) {
    $uvicornArguments += "--reload"
}

Write-Host "Starting backend at http://${BindAddress}:$Port"
& $pythonCommand @uvicornArguments
