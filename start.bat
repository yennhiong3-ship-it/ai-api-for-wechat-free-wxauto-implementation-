@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WeChat Bot

echo.
echo ==========================================
echo   WeChat Bot - Launcher
echo ==========================================
echo.

:: Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo Run install.bat first, or manually:
    echo   python -m venv .venv
    echo   .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)

:: Check .env config
if not exist ".env" (
    echo [WARN] .env file not found. Please create .env with your API key.
)

:: Launch
echo [INFO] Starting main.py ...
echo ------------------------------------------
.venv\Scripts\python.exe main.py
echo ------------------------------------------
echo.
echo [INFO] Process exited (code: %ERRORLEVEL%)
echo.
pause
