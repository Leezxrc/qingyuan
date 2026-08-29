@echo off
chcp 65001 >nul
echo ==========================================================
echo Qingyuan v5.8.4 version/protocol hotfix test
echo ==========================================================
"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\tools\test_version_hotfix_v584.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Hotfix test failed.
    pause
    exit /b 1
)
echo.
echo [OK] v5.8.4 version/protocol hotfix passed.
pause
