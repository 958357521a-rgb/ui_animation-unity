@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BUD UI Studio 安装与自检
echo 检查这台电脑上工作台要用的环境(只读检查;缺 Pillow 会自动装)。
echo.
set PY=
python -c "import sys" >nul 2>nul && set PY=python
if not defined PY py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY (
  echo [X] 没有可用的 Python。
  echo     装 Python 3.12:https://www.python.org/downloads/ ,安装时勾选 Add python.exe to PATH;
  echo     或者在 PowerShell 里运行:winget install Python.Python.3.12
  echo     装好后关掉这个窗口,再双击一次「安装与自检.bat」。
  pause
  exit /b 1
)
%PY% dev\setup_check.py
echo.
choice /c YN /n /m "要不要试跑一张 AI 重绘,确认 AI 重绘能用?(约半分钟起,共享的 ComfyUI 忙时要排队)[Y/N] "
if errorlevel 2 goto end
%PY% dev\setup_check.py --smoke
:end
pause
