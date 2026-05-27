# Ежедневный бэкап в Task Scheduler (от администратора):
# powershell -ExecutionPolicy Bypass -File .\scripts\schedule-backup.ps1

param(
    [string]$Time = "03:00",
    [string]$TaskName = "ChatBotAI-PostgresBackup"
)

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$BackupScript = Join-Path $BackendRoot "scripts\backup.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$BackupScript`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Задача $TaskName, $Time -> $BackupScript"
