@echo off
title Qingyuan Tray Dependency Installer
cd /d C:\MyAgent

echo ================================================
echo Installing Qingyuan tray dependencies...
echo ================================================
echo.

if not exist "C:\MyAgent\.venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment was not found.
    echo Expected:
    echo C:\MyAgent\.venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

"C:\MyAgent\.venv\Scripts\python.exe" -m pip install pystray pillow

if errorlevel 1 (
    echo.
    echo ================================================
    echo Installation failed.
    echo ================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================
echo Installation completed successfully.
echo ================================================
echo.
pause
