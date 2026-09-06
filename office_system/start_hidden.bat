@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Prison OA System - Background Start

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
if exist "%PROJECT_DIR%nextcloud_config.bat" call "%PROJECT_DIR%nextcloud_config.bat"

set "PYTHON_EXE=%PROJECT_DIR%python\python.exe"
set "PYTHONW_EXE=%PROJECT_DIR%python\pythonw.exe"
set "PYTHON_DIR=%PROJECT_DIR%python"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Portable Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%PYTHONW_EXE%" (
    echo [ERROR] Portable pythonw.exe not found: %PYTHONW_EXE%
    pause
    exit /b 1
)

set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\DLLs;%PATH%"
set "PYTHONPATH=%PROJECT_DIR%"
set "PYTHONIOENCODING=utf-8:backslashreplace"

if exist "%PROJECT_DIR%health_check.py" (
    echo [INFO] Running offline self-check...
    "%PYTHON_EXE%" "%PROJECT_DIR%health_check.py"
    if errorlevel 1 (
        echo.
        echo [ERROR] Self-check failed. Run install_win7_runtime.bat as Administrator if runtime errors are shown.
        echo.
        pause
        exit /b 1
    )
)

if exist "%PROJECT_DIR%stop.bat" (
    call "%PROJECT_DIR%stop.bat" --quiet
)

if not exist "data" mkdir data
if not exist "data\uploads" mkdir data\uploads
if not exist "logs" mkdir logs

echo [INFO] Starting server in background...
wscript.exe "%PROJECT_DIR%run_hidden.vbs"

echo.
echo [OK] Server started in background.
echo Local: http://127.0.0.1:5000
echo Logs : logs\server.log
echo Error: logs\server-error.log
echo.
start "" http://127.0.0.1:5000
ping 127.0.0.1 -n 3 >nul
exit /b 0
