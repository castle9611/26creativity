@echo off
chcp 65001 >nul 2>&1
title Flask Portable App

REM ============================================
REM Flask 便携版启动脚本 (Win7 兼容)
REM 不需要安装 Python / VC++ Redist
REM ============================================

set "ROOT=%~dp0"
set "PYTHON=%ROOT%python\python.exe"
set "APP=%ROOT%app\"

REM 环境变量 (修复 zipimport / 模块加载)
set PYTHON_IGNORE_IMPORT_FAILURE=1
set PYTHONWARNINGS=ignore

REM Flask 配置
set FLASK_APP=fix_flask_env.py
set FLASK_ENV=development
set FLASK_DEBUG=1
set FLASK_RUN_HOST=127.0.0.1
set FLASK_RUN_PORT=5000

echo.
echo ========================================
echo    Flask Portable on Win7
echo ========================================
echo.
echo Python : %PYTHON%
echo App    : %APP%%FLASK_APP%
echo URL    : http://127.0.0.1:5000
echo.

cd /d "%APP%"
if errorlevel 1 (
    echo [ERROR] Can't cd to APP dir: %APP%
    pause
    exit /b 1
)

REM 尝试 flask run
"%PYTHON%" -W ignore -m flask run --host=127.0.0.1 --port=5000

REM 如果 flask run 失败，直接执行 app
if errorlevel 1 (
    echo.
    echo [WARN] flask run failed, trying direct execute...
    echo.
    "%PYTHON%" -W ignore "%APP%%FLASK_APP%"
)

echo.
echo [INFO] App exited.
pause
