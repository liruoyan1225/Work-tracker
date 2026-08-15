@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   WorkTracker 后台记录 启动
echo ============================================
echo.

netstat -ano | findstr ":8765" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [提示] 后台服务已在运行，直接在浏览器打开 http://127.0.0.1:8765 即可查看
    start http://127.0.0.1:8765
    pause
    exit /b 0
)

echo [1/2] 检查依赖...
pip install -q -r requirements.txt

echo [2/2] 后台静默启动（无窗口，自动记录中）...
"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Start-Process -FilePath 'python' -ArgumentList 'main.py --headless' -WorkingDirectory '%CD%' -WindowStyle Hidden -RedirectStandardOutput '%CD%\data\app.log' -RedirectStandardError '%CD%\data\app.err.log'"

echo.
echo 已启动！浏览器打开 http://127.0.0.1:8765 可随时查看时间线
echo 想停止时运行 stop-bg.bat
echo.
pause
