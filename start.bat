@echo off
chcp 65001 >nul
cd /d "%~dp0"
title DeepSeek V4 微信机器人

echo.
echo ╔══════════════════════════════════════════╗
echo ║   🤖 DeepSeek V4 + 微信 智能机器人      ║
echo ║   Python 3.12  ^|  wxauto4  ^|  EasyOCR   ║
echo ╚══════════════════════════════════════════╝
echo.

:: 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境未找到
    echo 请先运行: python -m venv .venv
    echo 然后运行: .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)

:: 检查 .env
if not exist ".env" (
    echo [警告] 未找到 .env，请配置 DEEPSEEK_API_KEY
)

:: 启动
echo [启动] 正在运行 main.py ...
echo ───────────────────────────────────────────
.venv\Scripts\python.exe main.py
echo ───────────────────────────────────────────
echo.
echo [结束] 程序已退出 (错误码: %ERRORLEVEL%)
echo.
pause
