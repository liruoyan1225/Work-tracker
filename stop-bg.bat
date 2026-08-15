@echo off
cd /d "%~dp0"

echo 正在停止 WorkTracker 后台记录...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo 结束进程 PID %%p
    taskkill /PID %%p /F >nul 2>nul
)
echo 已停止。下次启动运行 start-bg.bat 即可。
pause
