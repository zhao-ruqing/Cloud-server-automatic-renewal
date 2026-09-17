@echo off
chcp 65001 >nul
cd /d "%~dp0.."

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM"') do set YM=%%i
if not exist "logs\%YM%" mkdir "logs\%YM%"

echo ========================================
echo Sanfeng / Abeiyun scheduled run
echo Dir: %CD%
echo Time: %DATE% %TIME%
echo ========================================

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found in PATH.
  echo Install Python and check "Add to PATH", then reopen CMD.
  pause
  exit /b 1
)

python main.py --scheduled
set EXITCODE=%ERRORLEVEL%

echo.
echo Finished with exit code %EXITCODE%
echo Log also appends to logs\%YM%\scheduled.log

>> "logs\%YM%\scheduled.log" echo ===== %DATE% %TIME% exit=%EXITCODE% =====

if not "%1"=="nopause" pause
exit /b %EXITCODE%
