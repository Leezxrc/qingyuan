@echo off
title Qingyuan Split Architecture
cd /d C:\MyAgent

echo ============================================================
echo Qingyuan Frontend + Brain Backend
echo ============================================================
echo.
echo Frontend will automatically start the local backend.
echo.
.\.venv\Scripts\python.exe agent.py
pause
