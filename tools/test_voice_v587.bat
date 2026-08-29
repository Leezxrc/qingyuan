@echo off
chcp 65001 >nul
echo ==========================================================
echo Qingyuan v5.8.7 Voice latency/barge/ASR guard test
echo ==========================================================
cd /d C:\MyAgent
"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\tools\test_voice_v587.py"
if errorlevel 1 (
    echo.
    echo [ERROR] v5.8.7 test failed.
    pause
    exit /b 1
)
echo.
echo [OK] v5.8.7 voice hotfix passed.
pause
