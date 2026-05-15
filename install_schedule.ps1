# 注册每天早上 8:40 启动「下班提醒」的 Windows 任务计划
# 使用：右键 -> 用 PowerShell 运行（普通权限即可，注册到当前用户）

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe).Source }
$target = Join-Path $scriptDir "off_reminder.py"

if (-not (Test-Path $target)) {
    Write-Host "找不到 off_reminder.py" -ForegroundColor Red
    exit 1
}

$taskName = "OffReminder_Morning"

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$target`" --morning"
$trigger = New-ScheduledTaskTrigger -Daily -At "08:40"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "每天 8:40 弹窗输入上班时间" -Force | Out-Null

Write-Host "已注册任务：$taskName  每天 08:40 启动" -ForegroundColor Green
Write-Host "执行：$py `"$target`" --morning"

# ---- 每月 1 号 09:00 静默更新节假日数据 ----
$updTask = "OffReminder_UpdateHolidays"
$updAction = New-ScheduledTaskAction -Execute $py -Argument "`"$target`" --update-holidays"
$updTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:00"
Register-ScheduledTask -TaskName $updTask -Action $updAction -Trigger $updTrigger `
    -Settings $settings -Description "每周自动更新中国节假日数据" -Force | Out-Null
Write-Host "已注册任务：$updTask  每周一 09:00 静默更新节假日" -ForegroundColor Green

Write-Host ""
Write-Host "（下班前 2 分钟的提醒会在你输入上班时间后自动注册）"
Read-Host "按回车键关闭"
