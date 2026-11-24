@echo off
title DilliTransit - Delhi Real-Time Bus Traffic Model & Planner
color 0A
cd /d "%~dp0"

echo ======================================================================
echo    DilliTransit - Delhi Real-Time Bus Traffic Model & Planner
echo ======================================================================
echo.
echo [1/3] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
python --version

echo.
echo [2/3] Launching web browser to http://localhost:8000 ...
start http://localhost:8000

echo.
echo [3/3] Starting DilliTransit HTTP Server on port 8000...
echo.
echo ======================================================================
echo   DilliTransit is now LIVE!
echo   - Web URL: http://localhost:8000
echo   - To stop the server, press Ctrl + C in this window.
echo ======================================================================
echo.

python server.py
pause
