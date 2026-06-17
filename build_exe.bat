@echo off
chcp 65001 >nul
title OakSeewoManager - Packaging to EXE
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
taskkill /f /im OakSeewoManager.exe 2>nul
timeout /t 2 /nobreak >nul

echo [*] Packaging OakSeewoManager.py to EXE...

:: Clean up old files to prevent PermissionError
if exist ".\OSM_exe\OakSeewoManager.exe" del /f /q ".\OSM_exe\OakSeewoManager.exe" 2>nul
if exist ".\build_temp" rmdir /s /q ".\build_temp" 2>nul

:: Use absolute path for icon (PyInstaller resolves relative paths against workpath)
set ICON_FLAG=
if exist "%~dp0Oak.ico" set ICON_FLAG=--icon "%~dp0Oak.ico"

pyinstaller --onefile --windowed --name "OakSeewoManager" %ICON_FLAG% --distpath ".\OSM_exe" --workpath ".\build_temp" --specpath ".\build_temp" OakSeewoManager.py

if %ERRORLEVEL% NEQ 0 (
    echo [Error] PyInstaller failed
    echo.
    echo Try running without --onefile:
    echo   pyinstaller --windowed --name "OakSeewoManager" --distpath ".\OSM_exe" OakSeewoManager.py
    pause
    exit /b 1
)

:: Copy supporting files
if exist ".\config.json" copy ".\config.json" ".\OSM_exe\config.json" >nul
if exist ".\Oak.ico" copy ".\Oak.ico" ".\OSM_exe\Oak.ico" >nul
copy "OakSeewoManager.bat" ".\OSM_exe\OakSeewoManager.bat" >nul
echo OakSeewoManager.bat >> ".\OSM_exe\.gitignore" 2>nul

:: Clean up build artifacts
if exist ".\build_temp" rmdir /s /q ".\build_temp"

echo.
echo ============================================
echo   Done! EXE is in .\OSM_exe\ folder
echo   File: OSM_exe\OakSeewoManager.exe
echo ============================================
echo.
echo Note: The EXE may trigger antivirus false positives
echo due to PyInstaller's nature.
echo.

pause
