@echo off
chcp 65001 >nul
title ScreenGuard - Packaging to EXE
cd /d "%~dp0"

echo ============================================
echo   ScreenGuard v3.0 - EXE Builder
echo ============================================
echo.

:: Check PyInstaller
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] PyInstaller not found, installing...
    pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo [Error] Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo [*] Packaging screen_guard.py to EXE...

set ICON=
if exist "Oak.ico" set ICON=--icon "Oak.ico"
if exist "icon.ico" set ICON=--icon "icon.ico"

pyinstaller --onefile --windowed --name "ScreenGuard" %ICON% --distpath ".\OSME" --workpath ".\build_temp" --specpath ".\build_temp" screen_guard.py

if %ERRORLEVEL% NEQ 0 (
    echo [Error] PyInstaller failed
    echo.
    echo Try running without --onefile:
    echo   pyinstaller --windowed --name "ScreenGuard" --distpath ".\OSME" screen_guard.py
    pause
    exit /b 1
)

:: Copy supporting files
if exist ".\config.json" copy ".\config.json" ".\OSME\config.json" >nul
copy "screen_guard.bat" ".\OSME\screen_guard.bat" >nul
echo screen_guard.bat >> ".\OSME\.gitignore" 2>nul

:: Clean up build artifacts
if exist ".\build_temp" rmdir /s /q ".\build_temp"

echo.
echo ============================================
echo   Done! EXE is in .\OSME\ folder
echo   File: OSME\ScreenGuard.exe
echo ============================================
echo.
echo Note: The EXE may trigger antivirus false positives
echo due to PyInstaller's nature.
echo.

pause
