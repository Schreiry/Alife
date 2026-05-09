@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [error] Failed to create virtual environment.
        echo Make sure Python 3.11+ is installed and on PATH.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo [setup] Upgrading pip...
python -m pip install --upgrade pip

echo [setup] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [error] Dependency installation failed.
    pause
    exit /b 1
)

echo [run] Starting simulation...
python main.py
set EXITCODE=%ERRORLEVEL%

echo.
echo [done] Simulation exited with code %EXITCODE%.
pause
endlocal
exit /b %EXITCODE%
