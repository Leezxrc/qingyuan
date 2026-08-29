@echo off
setlocal
cd /d C:\MyAgent
"C:\MyAgent\.venv\Scripts\python.exe" "C:\MyAgent\tools\test_voice_stability_v583.py"
if errorlevel 1 (
  echo.
  echo [ERROR] v5.8.3 voice stability smoke test failed.
  pause
  exit /b 1
)
echo.
echo [OK] v5.8.3 voice stability smoke test passed.
pause
