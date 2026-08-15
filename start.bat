@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)

echo [1/2] 检查依赖...
pip install -q -r requirements.txt

echo [2/2] 启动 WorkTracker...
python main.py %*

pause
