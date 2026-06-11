@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Prison OA System - Win7 Offline

echo ============================================
echo     Prison OA System v1.0.0
echo     Win7 64-bit Offline Portable Edition
echo ============================================
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: Check portable Python
set "PYTHON_EXE=%PROJECT_DIR%python\python.exe"
set "PYTHON_DIR=%PROJECT_DIR%python"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Portable Python not found.
    echo Expected: %PYTHON_EXE%
    echo.
    echo Please copy the complete office_system folder, including python\.
    echo.
    pause
    exit /b 1
)

:: Make bundled DLLs visible to Python extension modules on older Win7 systems.
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\DLLs;%PATH%"
set "PYTHONPATH=%PROJECT_DIR%"
set "PYTHONIOENCODING=utf-8:backslashreplace"

:: Run target-machine self-check before starting.
if exist "%PROJECT_DIR%health_check.py" (
    echo [INFO] Running offline self-check...
    "%PYTHON_EXE%" "%PROJECT_DIR%health_check.py"
    if errorlevel 1 (
        echo.
        echo [ERROR] Self-check failed. Please fix the items above first.
        if exist "%PROJECT_DIR%runtime_diagnose.py" (
            echo.
            echo [INFO] Running runtime diagnostics...
            "%PYTHON_EXE%" "%PROJECT_DIR%runtime_diagnose.py"
        )
        if exist "%PROJECT_DIR%install_win7_runtime.bat" (
            echo.
            echo [HINT] If diagnostics show _socket/_ctypes/_sqlite3 import errors,
            echo        right-click install_win7_runtime.bat and choose Run as administrator.
            echo        Restart Windows if prompted, then run start.bat again.
        )
        echo.
        pause
        exit /b 1
    )
    echo.
)

:: Stop any existing service first
if exist "%PROJECT_DIR%stop.bat" (
    echo [INFO] Stopping existing service...
    call "%PROJECT_DIR%stop.bat" --quiet
)

echo [INFO] Using built-in Python: %PYTHON_EXE%
echo.

:: Ensure data directories
if not exist "data" mkdir data
if not exist "data\uploads" mkdir data\uploads

:: Get local IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:IPv4') do (
    set "LOCAL_IP=%%a"
    set "LOCAL_IP=!LOCAL_IP: =!"
)

echo ============================================
echo     Starting server...
echo     Local:  http://127.0.0.1:5000
if defined LOCAL_IP echo     LAN:    http://!LOCAL_IP!:5000
echo     Login:  admin / admin123
echo     Press Ctrl+C to stop
echo ============================================
echo.

:: Open browser after a short delay while keeping the server in this window.
start "" cmd /c "ping 127.0.0.1 -n 3 >nul && start http://127.0.0.1:5000"

:: Run server via run.py (handles DB init + server start)
"%PYTHON_EXE%" run.py

echo.
echo [INFO] Server stopped
pause
