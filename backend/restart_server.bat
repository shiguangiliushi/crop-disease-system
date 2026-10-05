@echo off
echo 正在停止所有Python进程...
taskkill /F /IM python.exe /T >nul 2>&1

echo 正在清理日志文件...
if exist "logs" (
    del /F /Q "logs\*.log" >nul 2>&1
)

echo 正在启动Django开发服务器...
start "" cmd /k "cd /d %~dp0 && python manage.py runserver"

echo 服务已启动，按任意键退出...
pause >nul
