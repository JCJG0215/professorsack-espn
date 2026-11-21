@echo off
cd /d "%~dp0"
py -3 -m pip install --upgrade espn-api keyring tzdata
if errorlevel 1 (
  echo Dependency installation failed. Check Python 3 and your internet connection.
  pause
  exit /b 1
)
echo Setup complete. Double-click export_windows.bat.
pause
