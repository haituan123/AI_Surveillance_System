$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonCommand = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
Set-Location -LiteralPath $projectRoot

$env:PYTHONDONTWRITEBYTECODE = "1"
& $pythonCommand -m unittest discover -s backend/tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Backend tests failed."
}

Set-Location -LiteralPath (Join-Path $projectRoot "app_flutter")
flutter analyze
if ($LASTEXITCODE -ne 0) {
    throw "Flutter analysis failed."
}
flutter test
if ($LASTEXITCODE -ne 0) {
    throw "Flutter tests failed."
}

Write-Host "All project checks passed."
