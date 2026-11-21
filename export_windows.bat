@echo off
cd /d "%~dp0"
py -3 export_espn.py
if errorlevel 1 echo Export failed. Read error shown above.
pause
