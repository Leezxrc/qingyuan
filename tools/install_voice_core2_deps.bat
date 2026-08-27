@echo off
setlocal
chcp 65001 >nul

set "ROOT=C:\MyAgent"
set "PY=%ROOT%\stt_env\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] STT Python not found:
  echo %PY%
  pause
  exit /b 1
)

echo ============================================================
echo Qingyuan Voice Core 2.0 dependency installer
echo ============================================================
echo.
echo This installs into the existing stt_env only:
echo   - webrtcvad-wheels  ^(real-time VAD^)
echo   - pypinyin          ^(fuzzy wake-word matching^)
echo   - PyTorch CPU      ^(SenseVoice runtime^)
echo   - funasr 1.3.29     ^(SenseVoice runtime^)
echo   - modelscope        ^(SenseVoice model download/cache^)
echo.
echo It does NOT touch C:\MyAgent\data, memory, knowledge, RAG or skills.
echo SenseVoiceSmall may download its model on first use.
echo.
pause

"%PY%" -m pip install --upgrade webrtcvad-wheels pypinyin
if errorlevel 1 goto :fail

"%PY%" -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto :fail

"%PY%" -m pip install --upgrade "funasr==1.3.29" modelscope
if errorlevel 1 goto :fail

echo.
echo [OK] Voice Core 2.0 dependencies installed.
echo Restart Qingyuan. SenseVoice will load/download in the background;
echo Whisper remains available as fallback while it is loading.
echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] Dependency installation failed.
echo Qingyuan can still run with the existing Whisper fallback.
echo Copy the error above if you want help diagnosing it.
echo.
pause
exit /b 1
