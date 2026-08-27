@echo off
setlocal
cd /d C:\MyAgent

echo ============================================================
echo Qingyuan EXE Builder

echo Target: C:\MyAgent\Qingyuan.exe
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Missing C:\MyAgent\.venv\Scripts\python.exe
    pause
    exit /b 1
)

if not exist "qingyuan_launcher.py" (
    echo [ERROR] Missing C:\MyAgent\qingyuan_launcher.py
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller is not installed. Installing into .venv...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller install failed.
        pause
        exit /b 1
    )
)

set ICON_ARGS=
if exist "assets\qingyuan.ico" set ICON_ARGS=--icon "assets\qingyuan.ico"

if exist "build\Qingyuan" rmdir /s /q "build\Qingyuan"
if exist "dist\Qingyuan.exe" del /q "dist\Qingyuan.exe"

".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name Qingyuan ^
    %ICON_ARGS% ^
    qingyuan_launcher.py

if errorlevel 1 (
    echo.
    echo [ERROR] EXE build failed.
    pause
    exit /b 1
)

copy /Y "dist\Qingyuan.exe" "C:\MyAgent\Qingyuan.exe" >nul

echo.
echo [OK] Build complete:
echo C:\MyAgent\Qingyuan.exe
echo.
echo From now on, double-click Qingyuan.exe to start Qingyuan.
pause
endlocal
