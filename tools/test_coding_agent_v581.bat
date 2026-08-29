@echo off
setlocal
set "ROOT=C:\MyAgent"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "TEST=%ROOT%\tools\test_coding_agent_v581.py"

echo ==========================================================
echo Qingyuan v5.8.1 hotfix smoke test
echo ==========================================================

if not exist "%PY%" (
  echo [ERROR] Python not found: %PY%
  pause
  exit /b 1
)

if not exist "%TEST%" (
  echo [ERROR] Test script not found: %TEST%
  pause
  exit /b 1
)

"%PY%" "%TEST%"
if errorlevel 1 (
  echo.
  echo [ERROR] Hotfix smoke test failed.
  pause
  exit /b 1
)

echo.
echo [OK] v5.8.1 hotfix smoke test passed.
pause
