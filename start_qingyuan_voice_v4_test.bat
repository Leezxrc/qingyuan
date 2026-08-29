@echo off
setlocal
cd /d C:\MyAgent

echo ========================================
echo Qingyuan Voice Core 4 - Phase 1
echo ========================================

if not exist "C:\MyAgent\.venv\Scripts\python.exe" (
    echo ERROR: C:\MyAgent\.venv\Scripts\python.exe not found
    pause
    exit /b 1
)

if not exist "C:\MyAgent\qingyuan_voice_v4.py" (
    echo ERROR: C:\MyAgent\qingyuan_voice_v4.py not found
    pause
    exit /b 1
)

"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\qingyuan_voice_v4.py"

pause
