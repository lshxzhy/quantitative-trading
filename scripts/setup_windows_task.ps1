param(
    [string]$TaskName = "StockResearchDailyUpdate",
    [string]$At = "18:30"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RunScript = Join-Path $ProjectRoot "scripts\run_daily_update.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""

$Trigger = New-ScheduledTaskTrigger -Daily -At $At

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Description "Daily stock research data update" `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' at $At."

