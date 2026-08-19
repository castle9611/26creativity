@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "FFMPEG=%~dp0tools\ffmpeg\ffmpeg.exe"
if exist "%FFMPEG%" goto ffmpeg_ready
where ffmpeg.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] FFmpeg was not found.
    echo Put the Windows ffmpeg.exe at tools\ffmpeg\ffmpeg.exe,
    echo or add FFmpeg to PATH, then run this tool again.
    pause
    exit /b 1
)
set "FFMPEG=ffmpeg.exe"
:ffmpeg_ready

if "%~1"=="" (
    echo Usage:
    echo   convert_video.bat "D:\videos\sample.mov"
    echo   convert_video.bat "D:\videos"
    echo.
    echo You can also drag a video file or folder onto this script.
    pause
    exit /b 2
)

set "INPUT=%~f1"
if not exist "%INPUT%" (
    echo [ERROR] Input does not exist: "%INPUT%"
    pause
    exit /b 2
)

if exist "%INPUT%\NUL" goto convert_directory

set "OUTPUT_DIR=%~dp1converted"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
call :convert_one "%INPUT%" "%OUTPUT_DIR%\%~n1.mp4"
if errorlevel 1 exit /b 1
goto finished

:convert_directory
set "OUTPUT_DIR=%INPUT%\converted"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
set "CONVERT_FAILED=0"
for %%E in (mp4 mov m4v webm ogv avi wmv mkv) do (
    for %%F in ("%INPUT%\*.%%E") do if exist "%%~fF" call :convert_one "%%~fF" "%OUTPUT_DIR%\%%~nF.mp4" || set "CONVERT_FAILED=1"
)
if "%CONVERT_FAILED%"=="1" exit /b 1
goto finished

:convert_one
echo [INFO] Converting: %~nx1
"%FFMPEG%" -y -i "%~1" -map 0:v:0 -map 0:a:0? -c:v libx264 -pix_fmt yuv420p -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart "%~2"
if errorlevel 1 (
    echo [ERROR] Conversion failed: %~nx1
    exit /b 1
)
echo [OK] Created: %~2
exit /b 0

:finished
echo.
echo [DONE] Compatible videos are in: "%OUTPUT_DIR%"
pause
exit /b 0
