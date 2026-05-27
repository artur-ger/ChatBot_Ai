param(
    [switch]$WithTelegram,
    [switch]$SkipSmoke,
    [switch]$SkipGoLive,
    [switch]$Prod
)

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $BackendRoot

Set-Location $BackendRoot
& (Join-Path $BackendRoot "scripts\init-env.ps1") @PSBoundParameters

Set-Location $RepoRoot

Write-Host "Building and starting core stack..."
docker compose up -d --build

if ($WithTelegram) {
    $envContent = Get-Content (Join-Path $RepoRoot ".env") -Raw
    if ($envContent -notmatch "(?m)^TELEGRAM_BOT_TOKEN=.+") {
        Write-Warning "TELEGRAM_BOT_TOKEN is empty in .env — telegram profile may fail."
    }
    Write-Host "Starting telegram profile..."
    docker compose --profile telegram up -d --build
}

Write-Host "Waiting for backend health..."
$healthy = $false
for ($i = 1; $i -le 60; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/healthz" -TimeoutSec 5
        if ($h.status -eq "ok") {
            $r = Invoke-RestMethod -Uri "http://localhost:8000/readyz" -TimeoutSec 5
            if ($r.status -eq "ready") {
                $healthy = $true
                break
            }
        }
    } catch {
        # retry
    }
    Start-Sleep -Seconds 3
}
if (-not $healthy) {
    Write-Warning "Backend not ready. Check: docker logs chatbot-backend"
}

function Read-EnvValue {
    param([string]$Key)
    foreach ($line in Get-Content (Join-Path $RepoRoot ".env")) {
        if ($line -match "^$([regex]::Escape($Key))=(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return ""
}

if (-not $SkipSmoke) {
    $smokeArgs = @{
        AdminToken     = (Read-EnvValue "ADMIN_API_TOKEN")
        AdminUsername  = (Read-EnvValue "ADMIN_USERNAME")
        AdminPassword  = (Read-EnvValue "ADMIN_PASSWORD")
    }
    & (Join-Path $BackendRoot "scripts\smoke.ps1") @smokeArgs
}

if (-not $SkipGoLive) {
    $goLiveArgs = @{
        AdminToken     = (Read-EnvValue "ADMIN_API_TOKEN")
        AdminUsername  = (Read-EnvValue "ADMIN_USERNAME")
        AdminPassword  = (Read-EnvValue "ADMIN_PASSWORD")
    }
    & (Join-Path $BackendRoot "scripts\go-live-checklist.ps1") @goLiveArgs
}

Write-Host ""
Write-Host "Deploy completed."
Write-Host "  Chat:  http://localhost:8000/"
Write-Host "  Admin: http://localhost:8000/admin  (login: ADMIN_USERNAME / ADMIN_PASSWORD from .env)"
Write-Host "  Docs:  http://localhost:8000/docs"
