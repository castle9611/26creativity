@echo off
chcp 65001 >nul
title Enable Prison OA Auto Start

set "PROJECT_DIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\Prison OA System.lnk"

if not exist "%PROJECT_DIR%start_hidden.bat" (
    echo [ERROR] Missing start_hidden.bat
    pause
    exit /b 1
)

if not exist "%STARTUP%" mkdir "%STARTUP%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath='%PROJECT_DIR%start_hidden.bat'; $s.WorkingDirectory='%PROJECT_DIR%'; $s.WindowStyle=7; $s.Description='Start Prison OA System in background'; $s.Save()"

if errorlevel 1 (
    echo [WARN] PowerShell shortcut creation failed, using registry fallback...
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Prison OA System" /t REG_SZ /d "\"%PROJECT_DIR%start_hidden.bat\"" /f
)

echo.
echo [OK] Auto start enabled for current Windows user.
echo It will run start_hidden.bat on next login.
echo.
pause
