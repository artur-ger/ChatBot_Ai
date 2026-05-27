param(
    [string]$EnvPath = ""
)

$ErrorActionPreference = "Stop"

$BackendRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $BackendRoot
if (-not $EnvPath) {
    $EnvPath = Join-Path $RepoRoot ".env"
}
$ExamplePath = Join-Path $RepoRoot ".env.example"

if (-not (Test-Path $ExamplePath)) {
    throw "Missing .env.example at $ExamplePath"
}

if (-not (Test-Path $EnvPath)) {
    Copy-Item $ExamplePath $EnvPath
    Write-Host "Created $EnvPath from .env.example"
}

function Set-EnvValue {
    param(
        [string]$Key,
        [string]$Value
    )
    $pattern = "^(#\s*)?$([regex]::Escape($Key))=.*$"
    $line = "$Key=$Value"
    $content = Get-Content $EnvPath -Raw
    if ($content -match "(?m)^$([regex]::Escape($Key))=") {
        $content = [regex]::Replace($content, $pattern, $line, 1)
    } elseif ($content -match "(?m)^#\s*$([regex]::Escape($Key))=") {
        $content = [regex]::Replace($content, $pattern, $line, 1)
    } else {
        $content = $content.TrimEnd() + "`n$line`n"
    }
    Set-Content -Path $EnvPath -Value $content -NoNewline
}

function Get-EnvValue {
    param([string]$Key)
    foreach ($line in Get-Content $EnvPath) {
        if ($line -match "^$([regex]::Escape($Key))=(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return ""
}

if (-not (Get-EnvValue "ADMIN_API_TOKEN")) {
    $token = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))
    Set-EnvValue "ADMIN_API_TOKEN" $token
    Write-Host "Generated ADMIN_API_TOKEN"
}

if (-not (Get-EnvValue "ADMIN_USERNAME")) {
    Set-EnvValue "ADMIN_USERNAME" "admin"
    Write-Host "Set ADMIN_USERNAME=admin"
}

if (-not (Get-EnvValue "ADMIN_PASSWORD")) {
    $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $chars = for ($i = 0; $i -lt 24; $i++) { $alphabet[(Get-Random -Maximum $alphabet.Length)] }
    $pass = -join $chars
    Set-EnvValue "ADMIN_PASSWORD" $pass
    Write-Host "Generated ADMIN_PASSWORD (save it - it is shown once)"
    Write-Host "ADMIN_PASSWORD=$pass"
}

if (-not (Get-EnvValue "ADMIN_SESSION_SECRET")) {
    $secret = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))
    Set-EnvValue "ADMIN_SESSION_SECRET" $secret
    Write-Host "Generated ADMIN_SESSION_SECRET"
}

if (-not (Get-EnvValue "LLM_SETTINGS_ENCRYPTION_KEY")) {
    Push-Location $BackendRoot
    $fernet = & poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate LLM_SETTINGS_ENCRYPTION_KEY (is poetry installed?)"
    }
    Set-EnvValue "LLM_SETTINGS_ENCRYPTION_KEY" $fernet.Trim()
    Write-Host "Generated LLM_SETTINGS_ENCRYPTION_KEY"
}

if (-not (Get-EnvValue "CHAT_ACL_DISABLED")) {
    Set-EnvValue "CHAT_ACL_DISABLED" "true"
    Write-Host "Set CHAT_ACL_DISABLED=true (local web chat without signature)"
}

if (-not (Get-EnvValue "LLM_ALLOW_RULE_BASED_FALLBACK")) {
    Set-EnvValue "LLM_ALLOW_RULE_BASED_FALLBACK" "true"
    Write-Host "Set LLM_ALLOW_RULE_BASED_FALLBACK=true (dev fallback LLM)"
}

if (-not (Get-EnvValue "LLM_BOOTSTRAP_DEFAULT")) {
    Set-EnvValue "LLM_BOOTSTRAP_DEFAULT" "true"
    Write-Host "Set LLM_BOOTSTRAP_DEFAULT=true (seed rule_based integration on first start)"
}

if (-not (Get-EnvValue "PUBLIC_SHOW_ADMIN_LINK")) {
    Set-EnvValue "PUBLIC_SHOW_ADMIN_LINK" "false"
}

Write-Host ""
Write-Host "Env ready: $EnvPath"
Write-Host "Set TELEGRAM_BOT_TOKEN manually if you need the bot profile."
