@echo off
chcp 65001 >nul
echo ==========================================================
echo Qingyuan v5.8.5 RemoteVoiceProxy hotfix test
echo ==========================================================
"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\tools\test_remote_voice_proxy_v585.py"
if errorlevel 1 (
    echo.
    echo [ERROR] v5.8.5 hotfix test failed.
    pause
    exit /b 1
)
echo.
echo [OK] v5.8.5 RemoteVoiceProxy hotfix passed.
pause
