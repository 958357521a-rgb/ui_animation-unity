@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BUD UI Studio 局域网共享
echo 正在启动 BUD UI Studio 局域网共享(端口 8790)。这个窗口别关,关掉窗口就停止共享。
echo.
where python >nul 2>nul && (python dev\studio_server.py 8790 --lan) || (py -3 dev\studio_server.py 8790 --lan)
pause
