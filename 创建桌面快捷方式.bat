@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "dev\make_shortcut.ps1"
echo 双击桌面上的「BUD UI Studio」就能打开工作台。
pause
