@echo off
setlocal
chcp 65001 >nul
set "PY=C:\MyAgent\stt_env\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] %PY% not found.
  pause
  exit /b 1
)
"%PY%" "C:\MyAgent\tools\check_voice_core2.py"
echo.
pause
