@echo off
REM DRIVE — Launch script for Windows
REM Usage: run.bat [port]
set PORT=%1
if "%PORT%"=="" set PORT=8765

echo.
echo   DRIVE — AI SSD Guardian
echo.

python drive_main.py --port %PORT% --host 127.0.0.1
if errorlevel 1 (
    echo.
    echo Failed to start. Make sure Python and Flask are installed.
    echo Run: pip install -r requirements.txt
    pause
)