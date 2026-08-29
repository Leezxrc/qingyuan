@echo off
chcp 65001 >nul
cd /d C:\MyAgent

echo 正在启动清渊...
".venv\Scripts\python.exe" "qingyuan_launcher.py"

if errorlevel 1 (
    echo.
    echo 清渊启动失败，错误代码：%errorlevel%
    pause
)
