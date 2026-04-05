@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Sextant — Setup

echo.
echo  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found in PATH.
    echo.
    echo  Please install Python 3.10+ from:
    echo  https://www.python.org/downloads/
    echo.
    echo  During installation, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

python app\setup_env.py
pause
