@echo off
REM Create / update Windows Task: every 2 hours
REM Run this once on the NEW computer (as Administrator recommended)

set TASK_NAME=SanfengCloudAutoRenew
set BAT_PATH=%~dp0run_scheduled.bat

schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
schtasks /Create /TN "%TASK_NAME%" /TR "\"%BAT_PATH%\" nopause" /SC HOURLY /MO 2 /RL LIMITED /F

if errorlevel 1 (
  echo Failed. Try: right-click this file -^> Run as administrator
  pause
  exit /b 1
)

echo OK: task "%TASK_NAME%" created, every 2 hours.
echo Check: Task Scheduler -^> %TASK_NAME%
schtasks /Query /TN "%TASK_NAME%" /V /FO LIST | findstr /I "TaskName Status Next Schedule"
pause
