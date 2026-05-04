param(
    [switch]$RunTests = $true
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Poetry = "poetry"
Set-Location $ProjectRoot

Write-Host "[1/5] Configuring Poetry virtualenv in project (.venv)"
& $Poetry config virtualenvs.in-project true --local

Write-Host "[2/5] Selecting Python 3.12 for Poetry env"
& $Poetry env use 3.12

Write-Host "[3/5] Installing dependencies with Poetry"
& $Poetry install --with dev

Write-Host "[4/5] Applying Alembic migrations"
& $Poetry run alembic upgrade head

if ($RunTests) {
    Write-Host "[5/5] Running unit + integration + e2e smoke tests"
    & $Poetry run pytest tests/unit tests/integration tests/e2e -q
}
else {
    Write-Host "[5/5] Tests skipped"
}

Write-Host ""
Write-Host "Bootstrap completed."
Write-Host "Activate env:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "Run API:"
Write-Host "  poetry run uvicorn app.main:app --reload"
