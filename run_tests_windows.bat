@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run start_windows.bat once to install Python dependencies.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
pause
