@echo off
chcp 65001 >nul
cd /d "%~dp0"
title DeepSeek V4 微信机器人 — 一键安装

echo ╔══════════════════════════════════════════╗
echo ║   🤖 DeepSeek V4 + 微信 智能机器人      ║
echo ║         一键安装脚本                     ║
echo ╚══════════════════════════════════════════╝
echo.

:: ---- 1. 检查 Python ----
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9~3.12
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo [检测] Python %%i

:: ---- 2. 创建虚拟环境 ----
if not exist ".venv\Scripts\python.exe" (
    echo [安装] 创建虚拟环境 .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [完成] 虚拟环境已创建
) else (
    echo [跳过] 虚拟环境已存在
)

:: ---- 3. 升级 pip ----
echo [安装] 升级 pip ...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
echo [完成] pip 已升级

:: ---- 4. 安装依赖 ----
echo [安装] 安装项目依赖 ...
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [警告] 批量安装失败，尝试逐项安装 ...
    for /f "usebackq delims=" %%i in ("requirements.txt") do (
        set pkg=%%i
        setlocal enabledelayedexpansion
        if not "!pkg!"=="" if "!pkg:~0,1!" neq "#" (
            echo    -^> 安装 !pkg! ...
            .venv\Scripts\python.exe -m pip install "!pkg!" --quiet
        )
        endlocal
    )
)
echo [完成] 依赖安装完成

:: ---- 5. 创建 .env 模板（如果不存在）----
if not exist ".env" (
    echo DEEPSEEK_API_KEY=你的DeepSeek_API密钥 > .env
    echo DEEPSEEK_BASE_URL=https://api.deepseek.com >> .env
    echo [创建] .env 模板已生成，请编辑填入 DEEPSEEK_API_KEY
) else (
    echo [跳过] .env 已存在
)

:: ---- 6. 创建 blacklist.txt（如果不存在）----
if not exist "blacklist.txt" (
    type nul > blacklist.txt
    echo [创建] blacklist.txt
) else (
    echo [跳过] blacklist.txt 已存在
)

:: ---- 7. 验证关键依赖 ----
echo [验证] 检查依赖导入 ...
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; print('dotenv OK')" 2>nul && echo   [OK] dotenv || echo   [FAIL] dotenv
.venv\Scripts\python.exe -c "from openai import OpenAI; print('openai OK')" 2>nul && echo   [OK] openai || echo   [FAIL] openai
.venv\Scripts\python.exe -c "from wxauto4 import WeChat; print('wxauto4 OK')" 2>nul && echo   [OK] wxauto4 || echo   [FAIL] wxauto4
.venv\Scripts\python.exe -c "import easyocr; print('easyocr OK')" 2>nul && echo   [OK] easyocr || echo   [FAIL] easyocr
.venv\Scripts\python.exe -c "import PIL; print('Pillow OK')" 2>nul && echo   [OK] Pillow || echo   [FAIL] Pillow
.venv\Scripts\python.exe -c "import torch; print('torch OK')" 2>nul && echo   [OK] torch || echo   [FAIL] torch

echo.
echo ╔══════════════════════════════════════════╗
echo ║   🤖 DeepSeek V4 + 微信 智能机器人      ║
echo ║         安装完成                         ║
echo ╚══════════════════════════════════════════╝
echo.
echo 启动方式（任选其一）：
echo   1. 再次运行 install.bat（不传参数，自动安装+启动）
echo   2. .venv\Scripts\python.exe main.py
echo.
pause
