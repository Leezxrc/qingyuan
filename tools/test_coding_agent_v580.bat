@echo off
setlocal
set "ROOT=C:\MyAgent"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "TEST=%ROOT%\tools\test_coding_agent_v580.py"

echo ==========================================================
echo Qingyuan Coding Agent v5.8.0 smoke test
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
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [OK] Coding Agent smoke test passed.
) else (
  echo [ERROR] Coding Agent smoke test failed. Exit code: %RC%
)

pause
exit /b %RC%
