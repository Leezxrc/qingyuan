@echo off
chcp 65001 >nul
echo ==========================================================
echo Qingyuan v5.8.6 Voice Proxy compatibility test
echo ==========================================================
cd /d C:\MyAgent
"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\tools\test_voice_proxy_compat_v586.py"
if errorlevel 1 (
    echo.
    echo [ERROR] v5.8.6 compatibility test failed.
    pause
    exit /b 1
)
echo.
echo [OK] v5.8.6 Voice Proxy compatibility passed.
pause
