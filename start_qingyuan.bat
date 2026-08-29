@echo off
setlocal
cd /d C:\MyAgent

echo ========================================
echo Qingyuan launcher
echo ========================================

curl -s --max-time 2 http://127.0.0.1:8767/health >nul 2>&1
if not errorlevel 1 (
    echo Qingyuan is already running.
    timeout /t 2 /nobreak >nul
    exit /b 0
)

if not exist C:\MyAgent\qingyuan_launcher.py (
    echo ERROR: qingyuan_launcher.py not found.
    pause
    exit /b 1
)

if not exist C:\MyAgent\.venv\Scripts\python.exe (
    echo ERROR: Python not found.
    pause
    exit /b 1
)

echo Starting Qingyuan...
start "" /min C:\MyAgent\.venv\Scripts\python.exe C:\MyAgent\qingyuan_launcher.py

timeout /t 3 /nobreak >nul
exit /b 0
