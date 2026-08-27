@echo off
setlocal
chcp 65001 >nul
set "PY=C:\MyAgent\stt_env\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] %PY% not found.
  pause
  exit /b 1
)
echo Installing only WebRTC VAD + pinyin wake matching.
echo SenseVoice will NOT be installed; Whisper remains the ASR engine.
echo.
"%PY%" -m pip install --upgrade webrtcvad-wheels pypinyin
if errorlevel 1 (
  echo [ERROR] Installation failed.
  pause
  exit /b 1
)
echo [OK] Lightweight Voice Core 2.0 dependencies installed.
pause
