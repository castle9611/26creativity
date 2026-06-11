@echo off
chcp 65001 >nul
title Disable Prison OA Auto Start

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\Prison OA System.lnk"

if exist "%SHORTCUT%" del /f /q "%SHORTCUT%"
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Prison OA System" /f >nul 2>&1

echo.
echo [OK] Auto start disabled for current Windows user.
echo.
pause
