# Start the Airline Voice Agent backend (run from anywhere)
$BackendRoot = $PSScriptRoot
Set-Location $BackendRoot

$RepoVenv = Join-Path (Split-Path $BackendRoot -Parent) "venv\Scripts\Activate.ps1"
$LocalVenv = Join-Path $BackendRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $RepoVenv) {
    & $RepoVenv
} elseif (Test-Path $LocalVenv) {
    & $LocalVenv
}

uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
