@echo off
chcp 65001 >nul
title Prison OA System - Runtime Diagnose

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%python\python.exe"
set "PYTHON_DIR=%PROJECT_DIR%python"

cd /d "%PROJECT_DIR%"
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\DLLs;%PATH%"
set "PYTHONPATH=%PROJECT_DIR%"
set "PYTHONIOENCODING=utf-8:backslashreplace"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Portable Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%PROJECT_DIR%runtime_diagnose.py"
echo.
pause
