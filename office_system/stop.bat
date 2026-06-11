@echo off
chcp 65001 >nul
if "%1"=="--quiet" goto :stop_only
title Stopping Services

echo ============================================
echo     Stopping Prison OA System Services
echo ============================================
echo.

:kill_services
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:\=\\%"

:: Method 1: Kill by port 5000 via netstat + findstr (fast)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /C:":5000" ^| findstr /C:"LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1 && echo [OK] Killed PID %%a
)

:: Method 2: Kill python/pythonw processes whose command line contains this project's run.py
wmic process where "(name='python.exe' or name='pythonw.exe') and CommandLine like '%%%PROJECT_DIR%%%run.py%%'" get ProcessId /value 2>nul | findstr "ProcessId" >nul
if not errorlevel 1 (
    for /f "skip=1 tokens=2 delims==" %%a in ('wmic process where "(name='python.exe' or name='pythonw.exe') and CommandLine like '%%%PROJECT_DIR%%%run.py%%'" get ProcessId /value 2^>nul') do (
        if not "%%a"=="" (
            taskkill /F /PID %%a >nul 2>&1 && echo [OK] Killed PID %%a (run.py)
        )
    )
)

:: Method 3: Fallback - kill bundled python/pythonw inside this copied folder
wmic process where "(name='python.exe' or name='pythonw.exe') and ExecutablePath like '%%%PROJECT_DIR%%%python%%python%%.exe%%'" get ProcessId /value 2>nul | findstr "ProcessId" >nul
if not errorlevel 1 (
for /f "tokens=2 delims==" %%a in ('wmic process where "(name='python.exe' or name='pythonw.exe') and ExecutablePath like '%%%PROJECT_DIR%%%python%%python%%.exe%%'" get ProcessId /value 2^>nul') do (
    if not "%%a"=="" (
        taskkill /F /PID %%a >nul 2>&1 && echo [OK] Killed PID %%a (bundled python)
    )
)
)

if "%1"=="--quiet" exit /b 0

echo.
echo [OK] All services stopped
echo.
pause
exit /b 0

:stop_only
echo [INFO] Stopping existing service...
goto :kill_services
