@echo off
REM 一键安装/卸载 Windows 任务计划

if "%1"=="uninstall" goto uninstall

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_schedule.ps1"
goto end

:uninstall
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Unregister-ScheduledTask -TaskName 'OffReminder_Morning' -Confirm:$false -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName 'OffReminder_OffTime' -Confirm:$false -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName 'OffReminder_UpdateHolidays' -Confirm:$false -ErrorAction SilentlyContinue; Write-Host '已卸载任务' -ForegroundColor Yellow"
pause

:end
