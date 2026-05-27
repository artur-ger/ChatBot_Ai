param(
    [string]$OutputDir = ".\backups"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $OutputDir $timestamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

Write-Host "Backup directory: $target"

$pgDump = Join-Path $target "postgres.sql"
docker exec chatbot-postgres pg_dump -U chatbot chatbot_ai | Out-File -FilePath $pgDump -Encoding utf8
Write-Host "[OK] postgres dump -> $pgDump"

$meta = @{
    timestamp = $timestamp
    volumes   = @("postgres_data", "chroma_data", "uploads_data", "telegram_bot_data")
    note      = "For full restore also snapshot Docker volumes listed above."
}
$meta | ConvertTo-Json | Out-File -FilePath (Join-Path $target "backup-meta.json") -Encoding utf8

Write-Host "Backup completed."
