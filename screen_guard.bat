@echo off
cd /d "%~dp0"
python screen_guard.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Error] Python not found or error occurred.
    echo Make sure Python 3.x is installed and in PATH.
    echo If missing pywebview, run: pip install pywebview
    pause
)
