# Start the Airline Voice Agent backend from the repo root.
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$VenvActivate = Join-Path $Root "venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) { & $VenvActivate }

# Ensure `src` / `autogen_flow` are importable when cwd is the repo root
python -c "import src.main" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Fixing Python path (one-time): pip install -e ."
    pip install -e .
    $Pth = Join-Path $Root "venv\Lib\site-packages\airline_backend.pth"
    if (Test-Path (Join-Path $Root "venv")) {
        Set-Content -Path $Pth -Value (Join-Path $Root "backend") -Encoding ascii
    }
}

uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
