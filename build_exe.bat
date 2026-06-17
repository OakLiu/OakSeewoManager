@echo off
chcp 65001 >nul
title ScreenGuard - Packaging to EXE
cd /d "%~dp0"

echo ============================================
echo   OakSeewoManager Beta1.0 - EXE Builder
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

echo [*] Terminating old EXE instances...
taskkill /f /im ScreenGuard.exe 2>nul
timeout /t 2 /nobreak >nul

echo [*] Packaging screen_guard.py to EXE...

:: Clean up old files to prevent PermissionError
if exist ".\OSM_exe\ScreenGuard.exe" del /f /q ".\OSM_exe\ScreenGuard.exe" 2>nul
if exist ".\build_temp" rmdir /s /q ".\build_temp" 2>nul

:: Use absolute path for icon (PyInstaller resolves relative paths against workpath)
set ICON_FLAG=
if exist "%~dp0Oak.ico" set ICON_FLAG=--icon "%~dp0Oak.ico"

pyinstaller --onefile --windowed --name "ScreenGuard" %ICON_FLAG% --distpath ".\OSM_exe" --workpath ".\build_temp" --specpath ".\build_temp" screen_guard.py

if %ERRORLEVEL% NEQ 0 (
    echo [Error] PyInstaller failed
    echo.
    echo Try running without --onefile:
    echo   pyinstaller --windowed --name "ScreenGuard" --distpath ".\OSM_exe" screen_guard.py
    pause
    exit /b 1
)

:: Copy supporting files
if exist ".\config.json" copy ".\config.json" ".\OSM_exe\config.json" >nul
copy "screen_guard.bat" ".\OSM_exe\screen_guard.bat" >nul
echo screen_guard.bat >> ".\OSM_exe\.gitignore" 2>nul

:: Clean up build artifacts
if exist ".\build_temp" rmdir /s /q ".\build_temp"

echo.
echo ============================================
echo   Done! EXE is in .\OSM_exe\ folder
echo   File: OSM_exe\ScreenGuard.exe
echo ============================================
echo.
echo Note: The EXE may trigger antivirus false positives
echo due to PyInstaller's nature.
echo.

pause
