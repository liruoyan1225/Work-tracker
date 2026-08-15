"""
WorkTracker 入口：启动后台监控 + 本地 Flask 服务 + 桌面窗口。

用法:
  python main.py            # 默认打开桌面窗口
  python main.py --browser  # 在默认浏览器中打开（不弹桌面窗口）
"""

import sys
import threading
import time

from backend import config
from backend.server import App

HOST = "127.0.0.1"
PORT = 8765


def run_server(app: App):
    app.flask_app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)


def main():
    app = App()

    # 后台监控线程在 App 初始化时已启动
    threading.Thread(target=run_server, args=(app,), name="flask-server", daemon=True).start()

    # 等待服务就绪
    for _ in range(30):
        try:
            import requests
            requests.get(f"http://{HOST}:{PORT}/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.3)

    url = f"http://{HOST}:{PORT}/"

    # 后台静默模式：只跑服务+监控，不弹任何窗口
    if "--headless" in sys.argv:
        print(f"[WorkTracker] 后台模式启动，服务地址: {url}")
        print(f"[WorkTracker] 在浏览器打开 {url} 可随时查看记录")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            print("[WorkTracker] 已停止")
        return

    if "--browser" in sys.argv:
        import webbrowser
        print(f"已启动，请在浏览器访问: {url}")
        webbrowser.open(url)
        # 保持进程存活
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            pass
        return

    # 桌面窗口模式
    import webview
    window = webview.create_window(
        "WorkTracker · 科研工作记录助手",
        url,
        width=1180,
        height=780,
        min_size=(900, 620),
    )
    try:
        webview.start()
    except Exception as e:
        print(f"无法打开桌面窗口（{e}），请在浏览器访问 {url}")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
