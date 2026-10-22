@echo off
setlocal
cd /d "%~dp0"
echo [Member 2] Setting up Task Backend ...
if not exist ".venv\Scripts\python.exe" (
    py -m venv .venv
    if errorlevel 1 (
        echo Cannot create environment. Install Python with py launcher.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection.
    pause
    exit /b 1
)
echo Starting API at http://127.0.0.1:5000/
".venv\Scripts\python.exe" app.py
pause
