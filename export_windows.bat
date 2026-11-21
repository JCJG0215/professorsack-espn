@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  py -3 export_espn.py
) else (
  python export_espn.py
)
exit /b %ERRORLEVEL%
