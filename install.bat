@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

title Dependency Installer

set "PYTHON="
set "VENV_DIR=%~dp0.venv"
set "REQ_FILE=%~dp0requirements.txt"
set "ERR_COUNT=0"
set "HAS_TORCH=0"

echo.
echo ==========================================
echo   Dependency Installer
echo   Python 3.9~3.12 | wxauto4 | EasyOCR | PyTorch
echo ==========================================
echo.

:: Step 1: Detect Python
echo [Step 1/5] Detecting Python ...

for %%v in (python3.12 python3.11 python3.10 python3.9 python3 python) do (
    if "!PYTHON!"=="" (
        where %%v >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            for /f "delims=" %%p in ('where %%v 2^>nul') do set "PYTHON=%%p"
        )
    )
)

if "%PYTHON%"=="" (
    echo [ERROR] Python not found. Please install Python 3.9~3.12.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('"%PYTHON%" --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] Python found: %PYTHON%
echo [INFO] Version: %PY_VER%

for /f "tokens=1 delims=." %%a in ("%PY_VER%") do set "PY_MAJOR=%%a"
for /f "tokens=2 delims=." %%a in ("%PY_VER%") do set "PY_MINOR=%%a"

if %PY_MAJOR% lss 3 (
    echo [ERROR] Python version too low, need 3.9+
    pause & exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 9 (
    echo [ERROR] Python %PY_VER% is below 3.9, please upgrade
    pause & exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% gtr 12 (
    echo [WARN] Python %PY_VER% may not be compatible with wxauto4, recommend 3.9~3.12
)

echo [INFO] Upgrading pip ...
"%PYTHON%" -m pip install --upgrade pip --quiet 2>&1
if !ERRORLEVEL! neq 0 (
    echo [WARN] pip upgrade failed, continuing with current version
) else (
    echo [OK] pip upgraded
)
echo.

:: Step 2: Create virtual environment
echo [Step 2/5] Creating virtual environment (.venv) ...

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Virtual environment already exists, skipping
) else (
    echo [INFO] Creating .venv ...
    "%PYTHON%" -m venv "%VENV_DIR%" 2>"%TEMP%\venv_err.txt"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        type "%TEMP%\venv_err.txt" 2>nul
        echo.
        echo Try: "%PYTHON%" -m pip install virtualenv
        echo Then: virtualenv .venv
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
echo.

:: Step 3: Check requirements.txt
echo [Step 3/5] Checking requirements.txt ...

if not exist "%REQ_FILE%" (
    echo [ERROR] requirements.txt not found: %REQ_FILE%
    pause
    exit /b 1
)

echo [OK] requirements.txt found
echo   Dependencies:
for /f "usebackq delims=" %%l in ("%REQ_FILE%") do (
    set "line=%%l"
    set "line=!line: =!"
    if not "!line!"=="" if not "!line:~0,1!"=="#" echo     - !line!
)

findstr /i "torch" "%REQ_FILE%" >nul 2>&1
if !ERRORLEVEL! equ 0 set "HAS_TORCH=1"
echo.

:: Step 4: Install dependencies
echo [Step 4/5] Installing dependencies ...

echo [INFO] Upgrading build tools ...
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel --quiet 2>&1
if !ERRORLEVEL! neq 0 (
    echo [WARN] Build tools upgrade failed
    set /a ERR_COUNT+=1
) else (
    echo [OK] Build tools ready
)

:: PyTorch (CPU version from official source)
if "%HAS_TORCH%"=="1" (
    echo.
    echo --- PyTorch ---
    echo [INFO] Installing PyTorch (CPU) from official source ...
    echo [INFO] This may take several minutes ...

    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu 2>"%TEMP%\torch_err1.txt"
    if !ERRORLEVEL! neq 0 (
        echo [WARN] PyTorch install failed from primary source, trying fallback ...
        "%VENV_PYTHON%" -m pip install torch --extra-index-url https://download.pytorch.org/whl/cpu 2>"%TEMP%\torch_err2.txt"
        if !ERRORLEVEL! neq 0 (
            echo [ERROR] PyTorch installation failed.
            type "%TEMP%\torch_err2.txt" 2>nul
            set /a ERR_COUNT+=1
        ) else (
            echo [OK] PyTorch installed (fallback source)
        )
    ) else (
        echo [OK] PyTorch installed (CPU)
    )
    echo.
)

:: wxauto4 (open source edition)
echo --- wxauto4 (open source) ---
echo [INFO] Installing wxauto4 ...
"%VENV_PYTHON%" -m pip install wxauto4>=4.0.0 2>"%TEMP%\wxauto_err.txt"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] wxauto4 installation failed.
    type "%TEMP%\wxauto_err.txt" 2>nul
    echo.
    echo Possible causes:
    echo   1. wxauto4 requires Windows + WeChat client
    echo   2. Python version incompatible (need 3.9~3.12)
    echo   3. Network issue
    echo.
    echo Manual install: %VENV_PYTHON% -m pip install wxauto4
    set /a ERR_COUNT+=1
) else (
    echo [OK] wxauto4 installed
)
echo.

:: EasyOCR
echo --- EasyOCR ---
echo [INFO] Installing EasyOCR ...
"%VENV_PYTHON%" -m pip install easyocr>=1.7.0 2>"%TEMP%\easyocr_err.txt"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] EasyOCR installation failed.
    type "%TEMP%\easyocr_err.txt" 2>nul
    set /a ERR_COUNT+=1
) else (
    echo [OK] EasyOCR installed
)
echo.

:: OpenAI SDK
echo --- OpenAI SDK ---
echo [INFO] Installing openai ...
"%VENV_PYTHON%" -m pip install "openai>=1.0.0" 2>"%TEMP%\openai_err.txt"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] openai installation failed.
    type "%TEMP%\openai_err.txt" 2>nul
    set /a ERR_COUNT+=1
) else (
    echo [OK] openai installed
)
echo.

:: python-dotenv / Pillow
echo --- Other dependencies ---
echo [INFO] Installing python-dotenv, Pillow ...
"%VENV_PYTHON%" -m pip install "python-dotenv>=1.0.0" "Pillow>=10.0.0" 2>"%TEMP%\misc_err.txt"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Installation failed.
    type "%TEMP%\misc_err.txt" 2>nul
    set /a ERR_COUNT+=1
) else (
    echo [OK] python-dotenv, Pillow installed
)
echo.

:: Step 5: Verify imports
echo [Step 5/5] Verifying installation ...

set "VERIFY_OK=1"

echo [Check] openai ...
"%VENV_PYTHON%" -c "import openai; print('  version:', openai.__version__)" 2>nul || (
    echo   [FAIL] openai import failed
    set "VERIFY_OK=0"
)

echo [Check] dotenv ...
"%VENV_PYTHON%" -c "from dotenv import load_dotenv; print('  OK')" 2>nul || (
    echo   [FAIL] python-dotenv import failed
    set "VERIFY_OK=0"
)

echo [Check] wxauto4 ...
"%VENV_PYTHON%" -c "from wxauto4 import WeChat; print('  OK')" 2>nul || (
    echo   [FAIL] wxauto4 import failed
    echo   Note: wxauto4 requires Windows and WeChat client
    set "VERIFY_OK=0"
)

echo [Check] easyocr ...
"%VENV_PYTHON%" -c "import easyocr; print('  version:', easyocr.__version__)" 2>nul || (
    echo   [FAIL] easyocr import failed
    set "VERIFY_OK=0"
)

echo [Check] torch ...
"%VENV_PYTHON%" -c "import torch; print('  version:', torch.__version__)" 2>nul || (
    echo   [FAIL] PyTorch import failed
    set "VERIFY_OK=0"
)

echo [Check] Pillow ...
"%VENV_PYTHON%" -c "from PIL import Image; print('  OK')" 2>nul || (
    echo   [FAIL] Pillow import failed
    set "VERIFY_OK=0"
)

echo.

:: Final report
echo ==========================================
if "%VERIFY_OK%"=="1" if %ERR_COUNT% equ 0 (
    echo   SUCCESS: All dependencies installed.
    echo ==========================================
    echo.
    echo Next steps:
    echo   1. Configure .env file with your API key
    echo   2. Run start.bat to launch
    echo.
) else (
    echo   WARNING: Installation completed with issues.
    echo ==========================================
    echo.
    if %ERR_COUNT% gtr 0 echo   Install failures: %ERR_COUNT% package(s)
    if "%VERIFY_OK%"=="0" echo   Import verification failed, check errors above
    echo.
    echo Troubleshooting:
    echo   1. Network: try China mirror
    echo      %VENV_PYTHON% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    echo   2. wxauto4 requires Windows 64-bit + WeChat client
    echo      GitHub: https://github.com/cluic/wxauto
    echo.
    echo   3. PyTorch CPU manual install:
    echo      %VENV_PYTHON% -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    echo.
    echo   4. EasyOCR will download models on first run (~200MB)
    echo.
)

:: Cleanup temp files
del "%TEMP%\venv_err.txt" "%TEMP%\torch_err1.txt" "%TEMP%\torch_err2.txt" "%TEMP%\wxauto_err.txt" "%TEMP%\easyocr_err.txt" "%TEMP%\openai_err.txt" "%TEMP%\misc_err.txt" 2>nul

endlocal
echo ==========================================
echo.
pause
exit /b %ERR_COUNT%
