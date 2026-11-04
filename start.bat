@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ====================================================================
echo 🎬 Starting ClipSnap on Windows...
echo ====================================================================

REM 1. Check Python installation
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo ❌ Python was not found on your system PATH!
        echo    Please install Python 3.11+ from https://python.org
        echo    IMPORTANT: Check the box "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
)

REM 2. Create Python venv if missing
if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Creating Python virtual environment (venv)...
    python -m venv venv
    if errorlevel 1 py -m venv venv
    set VENV_CREATED=1
)

REM Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo ❌ Could not activate virtual environment in venv\
    pause
    exit /b 1
)

REM 3. Install requirements if needed
if "%VENV_CREATED%"=="1" (
    set NEED_PIP=1
) else if not exist "venv\.installed" (
    set NEED_PIP=1
) else (
    set NEED_PIP=0
)

if "%NEED_PIP%"=="1" (
    echo [2/3] Installing Python requirements from backend\requirements.txt...
    pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo ❌ Failed to install Python dependencies.
        pause
        exit /b 1
    )
    echo installed > venv\.installed
)

REM 4. Start unified server via run.py
echo [3/3] Launching ClipSnap Server...
python run.py

if errorlevel 1 (
    echo.
    echo ❌ ClipSnap Server stopped with an error.
    pause
)
