@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ---------------------------------------------------------------
REM  ALife / E-Life launcher
REM  Runs the unified observatory process (single Python process,
REM  internally hosts these threads in parallel):
REM    1. simulation thread        (Simulation + Brain + numba kernel)
REM    2. telemetry writer thread  (SQLite, buffered, 2s flush)
REM    3. FastAPI HTTP server      (uvicorn worker)
REM    4. WebSocket live stream    (starlette / uvicorn)
REM    5. browser auto-launch      (default browser, http://127.0.0.1:8765)
REM
REM  Args supplied to run.bat are forwarded to main.py. Examples:
REM    run.bat                          → observatory (default)
REM    run.bat --gui                    → legacy pygame fallback
REM    run.bat --headless               → no UI
REM    run.bat --benchmark 3000         → 3000 ticks + profiler dump
REM    run.bat --experiment survival_arena --ticks 2000 --out r.json
REM    run.bat --safe-mode              → shrunk pop + minimal observability
REM ---------------------------------------------------------------

cd /d "%~dp0"

echo.
echo [alife] working directory: %CD%

if not exist ".venv\Scripts\python.exe" (
    echo [setup] creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [error] failed to create virtual environment.
        echo         make sure Python 3.11+ is installed and on PATH.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

REM Pip install only when requirements changed.
set "REQ_MARKER=.venv\.alife_requirements_installed"
set "REINSTALL=0"
if not exist "%REQ_MARKER%" set "REINSTALL=1"
if exist "requirements.txt" if exist "%REQ_MARKER%" (
    for %%R in (requirements.txt) do set "REQ_TIME=%%~tR"
    for %%M in (%REQ_MARKER%) do set "MARK_TIME=%%~tM"
    if not "!REQ_TIME!"=="!MARK_TIME!" set "REINSTALL=1"
)

if "%REINSTALL%"=="1" (
    echo [setup] upgrading pip...
    python -m pip install --upgrade pip --quiet
    echo [setup] installing dependencies...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [error] dependency installation failed.
        pause
        exit /b 1
    )
    echo installed > "%REQ_MARKER%"
)

REM ---- port hygiene ---------------------------------------------------
REM  The observatory listens on 8765. If a previous run is still alive
REM  (Ctrl-Break orphan, IDE keeping it open, etc.) the new uvicorn will
REM  fail to bind and the browser sees an empty page. We detect this
REM  here and offer to free the port before launching.
set "ALIFE_PORT=8765"
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%ALIFE_PORT% .*LISTENING"') do (
    if not defined PORT_PID set "PORT_PID=%%P"
)
if defined PORT_PID (
    echo.
    echo [warn] port %ALIFE_PORT% is held by PID %PORT_PID%
    set /p KILLIT="       kill it and continue? [Y/n] "
    if /i not "!KILLIT!"=="n" (
        taskkill /F /PID %PORT_PID% >nul 2>&1
        if errorlevel 1 (
            echo [warn] could not kill PID %PORT_PID% — main.py will fall back to next free port.
        ) else (
            echo [ok] freed port %ALIFE_PORT%.
        )
    )
)

echo.
echo [alife] starting unified observatory process
if "%~1"=="" (
    echo         args: ^(default: --ui^)
) else (
    echo         args: %*
)
echo.

REM PYTHONIOENCODING ensures Russian/unicode prints don't blow up on
REM Windows consoles that default to cp1251.
set PYTHONIOENCODING=utf-8
python main.py %*
set EXITCODE=%ERRORLEVEL%

echo.
if "%EXITCODE%"=="0" (
    echo [alife] exited cleanly.
) else (
    echo [alife] exited with code %EXITCODE% — see traceback above.
)
echo.
pause
endlocal
exit /b %EXITCODE%
