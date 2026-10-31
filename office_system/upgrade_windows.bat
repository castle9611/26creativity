@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "TARGET_DIR=%~1"
if "%TARGET_DIR%"=="" (
    echo Usage: upgrade_windows.bat C:\path\to\existing\office_system
    exit /b 1
)
for %%I in ("%PACKAGE_DIR%.") do set "PACKAGE_DIR=%%~fI"
for %%I in ("%TARGET_DIR%") do set "TARGET_DIR=%%~fI"
if /I "%PACKAGE_DIR%"=="%TARGET_DIR%" (
    echo [ERROR] Extract the upgrade package to a separate directory.
    exit /b 1
)
if not exist "%TARGET_DIR%\data\database.db" (
    echo [ERROR] Existing database not found.
    exit /b 1
)
if not exist "%TARGET_DIR%\python\python.exe" (
    echo [ERROR] Existing portable Python not found.
    exit /b 1
)

echo [1/5] Stop existing service
call "%TARGET_DIR%\stop.bat" --quiet
echo [2/5] Back up existing database
"%TARGET_DIR%\python\python.exe" "%TARGET_DIR%\backup.py" backup
if errorlevel 1 exit /b 1
echo [3/5] Copy application files
xcopy "%PACKAGE_DIR%\app" "%TARGET_DIR%\app" /E /I /Y /Q >nul
if errorlevel 1 exit /b 1
for %%F in (run.py wsgi.py migrate.py health_check.py backup.py start.bat start_hidden.bat stop.bat status.bat convert_video.bat) do (
    copy /Y "%PACKAGE_DIR%\%%F" "%TARGET_DIR%\%%F" >nul
    if errorlevel 1 exit /b 1
)
echo [4/5] Migrate existing database
pushd "%TARGET_DIR%"
"python\python.exe" migrate.py
if errorlevel 1 (
    popd
    exit /b 1
)
popd
echo [5/5] Start service
call "%TARGET_DIR%\start.bat"
echo [OK] Upgrade complete. Existing data and Python were preserved.
