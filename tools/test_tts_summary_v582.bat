@echo off
setlocal
cd /d C:\MyAgent

echo ==========================================================
echo Qingyuan v5.8.2 TTS spoken-summary smoke test
echo ==========================================================

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\test_tts_summary_v582.py"
) else (
  python "tools\test_tts_summary_v582.py"
)

if errorlevel 1 (
  echo.
  echo [ERROR] v5.8.2 smoke test failed.
  pause
  exit /b 1
)

echo.
echo [OK] v5.8.2 spoken-summary smoke test passed.
pause
