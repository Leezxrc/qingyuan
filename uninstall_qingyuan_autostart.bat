@echo off
chcp 65001 >nul
title 取消清渊开机自启

set "TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\qingyuan_autostart.vbs"

echo ================================================
echo 正在取消清渊 Windows 登录自启
echo ================================================

if exist "%TARGET%" (
    del /Q "%TARGET%"
    echo.
    echo [完成] 已取消清渊 Windows 登录自启。
) else (
    echo.
    echo [提示] 没有找到清渊的自启项。
)

echo.
pause
