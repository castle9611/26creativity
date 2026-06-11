@echo off
chcp 65001 >nul
title Install Win7 Runtime Dependencies

set "PROJECT_DIR=%~dp0"
set "RUNTIME_DIR=%PROJECT_DIR%runtime_install"
set "KB=%RUNTIME_DIR%\Windows6.1-KB2999226-x64.msu"
set "VC=%RUNTIME_DIR%\vc_redist.x64.exe"

echo ============================================
echo   Install Win7 Runtime Dependencies
echo ============================================
echo.
echo This installs:
echo   1. KB2999226 Universal C Runtime for Windows 7 SP1 x64
echo   2. Microsoft Visual C++ 2015 Redistributable x64
echo.
echo Please run this file as Administrator on the target Win7 computer.
echo.

if not exist "%KB%" (
    echo [ERROR] Missing %KB%
    pause
    exit /b 1
)

if not exist "%VC%" (
    echo [ERROR] Missing %VC%
    pause
    exit /b 1
)

echo [INFO] Installing KB2999226...
wusa.exe "%KB%" /quiet /norestart
set "KB_RC=%ERRORLEVEL%"
echo [INFO] KB2999226 installer exit code: %KB_RC%
echo.

echo [INFO] Installing VC++ 2015 Redistributable x64...
"%VC%" /install /quiet /norestart
set "VC_RC=%ERRORLEVEL%"
echo [INFO] VC++ installer exit code: %VC_RC%
echo.

echo ============================================
echo   Runtime install finished
echo ============================================
echo If either installer asks for restart, restart Windows 7 first.
echo Then run start.bat again.
echo.
pause
