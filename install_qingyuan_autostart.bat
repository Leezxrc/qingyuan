@echo off
chcp 65001 >nul
title 安装清渊开机自启

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SOURCE=C:\MyAgent\qingyuan_autostart.vbs"
set "TARGET=%STARTUP%\qingyuan_autostart.vbs"

echo ================================================
echo 正在安装清渊 Windows 登录自启
echo ================================================

if not exist "%SOURCE%" (
    echo [错误] 找不到：
    echo %SOURCE%
    echo.
    pause
    exit /b 1
)

copy /Y "%SOURCE%" "%TARGET%" >nul

if errorlevel 1 (
    echo.
    echo [失败] 无法写入 Startup 文件夹。
    pause
    exit /b 1
)

echo.
echo [完成] 清渊已加入 Windows 登录自启。
echo.
echo 自启文件：
echo %TARGET%
echo.
echo 下次登录 Windows 时会自动启动清渊。
echo.
pause
