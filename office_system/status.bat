@echo off
chcp 65001 >nul
title Prison OA System - Status

echo ============================================
echo   Prison OA System Status
echo ============================================
echo.

netstat -ano | findstr /C:":5000" | findstr /C:"LISTENING" >nul
if errorlevel 1 (
    echo [STOPPED] Port 5000 is not listening.
) else (
    echo [RUNNING] Port 5000 is listening.
    echo.
    netstat -ano | findstr /C:":5000" | findstr /C:"LISTENING"
)

echo.
echo Logs:
echo   logs\server.log
echo   logs\server-error.log
echo.
pause
