@echo off
chcp 65001 >nul
cd /d C:\MyAgent
"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\tools\test_voice_core3_phase13.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Voice Core 3 Phase 1.3 test failed.
    pause
    exit /b 1
)
echo.
echo [OK] Voice Core 3 Phase 1.3 passed.
pause
