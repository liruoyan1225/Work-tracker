"""
Flask 后端：提供本地 API 给前端 Web UI 调用。
同时持有 ActivityMonitor 实例，启动/停止后台监控。
"""

import datetime
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

from . import config as config_mod
from . import storage, reporter
from .ai import AIClient, AIError, DEFAULT_PROVIDERS
from .monitor import ActivityMonitor, get_idle_seconds

STATIC_DIR = os.path.join(config_mod.APP_DIR, "static")


class App:
    def __init__(self):
        self.cfg = config_mod.load_config()
        self.monitor = None
        self.flask_app = Flask(__name__, static_folder=None)
        self._register_routes()
        self._apply_cfg()

    # ---------- 配置 ----------

    def _apply_cfg(self):
        m = self.cfg.get("monitor", {})
        self.monitor = ActivityMonitor(
            journal_dir=self.cfg.get("journal_dir", ""),
            poll_interval=m.get("poll_interval", 5),
            idle_threshold=m.get("idle_threshold", 180),
            flush_interval=m.get("flush_interval", 60),
        )
        if m.get("enabled", True):
            self.monitor.start()

    def _save_cfg(self):
        config_mod.save_config(self.cfg)

    def _ai(self) -> AIClient:
        return AIClient(self.cfg.get("ai", {}))

    # ---------- 路由 ----------

    def _register_routes(self):
        app = self.flask_app

        @app.route("/")
        def index():
            return send_from_directory(STATIC_DIR, "index.html")

        @app.route("/<path:filename>")
        def static_files(filename):
            return send_from_directory(STATIC_DIR, filename)

        # 配置
        @app.route("/api/config", methods=["GET"])
        def get_config():
            cfg = {
                "journal_dir": self.cfg.get("journal_dir", ""),
                "ai": {
                    "enabled": self.cfg.get("ai", {}).get("enabled", False),
                    "base_url": self.cfg.get("ai", {}).get("base_url", ""),
                    "api_key": self.cfg.get("ai", {}).get("api_key", ""),
                    "model": self.cfg.get("ai", {}).get("model", ""),
                    "temperature": self.cfg.get("ai", {}).get("temperature", 0.7),
                },
                "monitor": {
                    "enabled": self.cfg.get("monitor", {}).get("enabled", True),
                    "poll_interval": self.cfg.get("monitor", {}).get("poll_interval", 5),
                    "idle_threshold": self.cfg.get("monitor", {}).get("idle_threshold", 180),
                },
                "providers": DEFAULT_PROVIDERS,
            }
            return jsonify(cfg)

        @app.route("/api/config", methods=["POST"])
        def save_config():
            data = request.get_json(force=True)
            if "journal_dir" in data:
                self.cfg["journal_dir"] = str(data["journal_dir"])
            ai = data.get("ai")
            if ai is not None:
                self.cfg.setdefault("ai", {})
                for k, v in ai.items():
                    if k == "api_key" and not v and self.cfg["ai"].get("api_key"):
                        continue
                    self.cfg["ai"][k] = v
            mono = data.get("monitor")
            if mono is not None:
                self.cfg.setdefault("monitor", {})
                for k, v in mono.items():
                    self.cfg["monitor"][k] = v
            self._save_cfg()
            self._apply_cfg()
            return jsonify({"ok": True})

        @app.route("/api/ai/test", methods=["POST"])
        def ai_test():
            data = request.get_json(force=True) or {}
            cfg = self.cfg.get("ai", {}).copy()
            for k in ("base_url", "api_key", "model"):
                if data.get(k):
                    cfg[k] = data[k]
            cfg["enabled"] = True
            try:
                result = AIClient(cfg).test()
                return jsonify({"ok": True, "reply": result})
            except AIError as e:
                return jsonify({"ok": False, "error": str(e)})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        # 监控状态
        @app.route("/api/status", methods=["GET"])
        def status():
            return jsonify({
                "monitor_running": bool(self.monitor and self.monitor._thread and self.monitor._thread.is_alive()),
                "idle_seconds": get_idle_seconds(),
                "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        @app.route("/api/monitor/toggle", methods=["POST"])
        def monitor_toggle():
            data = request.get_json(force=True) or {}
            enabled = bool(data.get("enabled", True))
            self.cfg.setdefault("monitor", {})["enabled"] = enabled
            self._save_cfg()
            if enabled:
                self.monitor.start()
            else:
                self.monitor.stop()
            return jsonify({"ok": True, "enabled": enabled})

        # 日期与活动
        @app.route("/api/dates", methods=["GET"])
        def dates():
            jd = self.cfg.get("journal_dir", "")
            return jsonify({"dates": storage.all_available_dates(jd)})

        @app.route("/api/activities", methods=["GET"])
        def activities():
            date = request.args.get("date", datetime.date.today().strftime("%Y-%m-%d"))
            jd = self.cfg.get("journal_dir", "")
            records = storage.load_activities(jd, date)
            summary = storage.summarize_activities(records)
            journal = storage.read_daily_journal(jd, date)
            return jsonify({
                "date": date,
                "records": records,
                "summary": summary,
                "journal": journal,
            })

        @app.route("/api/notes", methods=["POST"])
        def add_note():
            data = request.get_json(force=True)
            content = str(data.get("content", "")).strip()
            if not content:
                return jsonify({"ok": False, "error": "内容不能为空"}), 400
            when = None
            if data.get("time"):
                try:
                    when = datetime.datetime.fromisoformat(data["time"])
                except Exception:
                    when = None
            record = self.monitor.add_note(content, when=when) if self.monitor else None
            if record is None:
                jd = self.cfg.get("journal_dir", "")
                when = when or datetime.datetime.now()
                record = {"kind": "note", "time": when.strftime("%Y-%m-%dT%H:%M:%S"), "content": content}
                storage.append_activity(jd, when.strftime("%Y-%m-%d"), record)
            return jsonify({"ok": True, "record": record})

        # 范围统计（周/月用）
        @app.route("/api/stats/range", methods=["GET"])
        def stats_range():
            start = request.args.get("start")
            end = request.args.get("end")
            if not start or not end:
                return jsonify({"ok": False, "error": "缺少 start/end"}), 400
            jd = self.cfg.get("journal_dir", "")
            by_date = storage.activities_in_range(jd, start, end)
            all_records = [r for d in sorted(by_date) for r in by_date[d]]
            return jsonify({
                "ok": True,
                "summary": storage.summarize_activities(all_records),
                "days": len(by_date),
                "dates": sorted(by_date),
            })

        # 生成报告
        @app.route("/api/generate", methods=["POST"])
        def generate():
            data = request.get_json(force=True)
            kind = data.get("kind", "日报")
            extra = data.get("extra_notes", "")
            jd = self.cfg.get("journal_dir", "")
            ai = self._ai()
            try:
                if kind == "日报":
                    date = data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
                    content = reporter.generate_daily(ai, jd, date, extra_notes=extra)
                    title = f"{date} 科研日报"
                elif kind == "周报":
                    start, end = _resolve_week(data)
                    content = reporter.generate_weekly(ai, jd, start, end, extra_notes=extra)
                    title = f"{start} 至 {end} 科研周报"
                elif kind == "月报":
                    month = data.get("month", datetime.date.today().strftime("%Y-%m"))
                    content = reporter.generate_monthly(ai, jd, month, extra_notes=extra)
                    title = f"{month} 科研月报"
                else:
                    return jsonify({"ok": False, "error": "未知报告类型"}), 400
            except AIError as e:
                return jsonify({"ok": False, "error": str(e)}), 500
            except Exception as e:
                return jsonify({"ok": False, "error": f"生成失败: {e}"}), 500
            return jsonify({"ok": True, "content": content, "title": title, "kind": kind})

        # 保存报告
        @app.route("/api/save-report", methods=["POST"])
        def save_report():
            data = request.get_json(force=True)
            kind = data.get("kind", "日报")
            content = data.get("content", "")
            date = data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
            if kind == "月报":
                date = data.get("month", date)
            jd = self.cfg.get("journal_dir", "")
            path = storage.save_report(jd, kind, date, content)
            return jsonify({"ok": True, "path": path})

        @app.route("/api/reports", methods=["GET"])
        def reports():
            jd = self.cfg.get("journal_dir", "")
            return jsonify({"reports": storage.list_reports(jd)})

        @app.route("/api/report", methods=["GET"])
        def report_content():
            jd = self.cfg.get("journal_dir", "")
            path = request.args.get("path", "")
            full = os.path.join(jd, "reports", os.path.basename(path))
            if os.path.exists(full):
                with open(full, "r", encoding="utf-8") as f:
                    return jsonify({"ok": True, "name": os.path.basename(full), "content": f.read()})
            return jsonify({"ok": False, "error": "文件不存在"}), 404

        @app.route("/api/journal/save", methods=["POST"])
        def journal_save():
            data = request.get_json(force=True)
            date = data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
            content = data.get("content", "")
            jd = self.cfg.get("journal_dir", "")
            path = storage.daily_journal_path(jd, date)
            os.makedirs(jd, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return jsonify({"ok": True, "path": path})

        @app.route("/api/journal/append", methods=["POST"])
        def journal_append():
            data = request.get_json(force=True)
            date = data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
            section = data.get("section", "## 📌 今日进展")
            content = data.get("content", "")
            jd = self.cfg.get("journal_dir", "")
            path = storage.daily_journal_path(jd, date)
            os.makedirs(jd, exist_ok=True)
            text = f"- {content}\n"
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    body = f.read()
                if section in body:
                    body = body.replace(section, section + "\n" + text, 1)
                else:
                    body = body.rstrip() + "\n\n" + section + "\n" + text
            else:
                body = f"# 每日科研复盘 - {date}\n\n{section}\n{text}"
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            return jsonify({"ok": True, "path": path})


def _resolve_week(data: dict) -> tuple:
    start = data.get("start")
    end = data.get("end")
    if not start or not end:
        today = datetime.date.today()
        start = storage.date_str(today - datetime.timedelta(days=today.weekday()))
        end = storage.date_str(today)
    return start, end


def create_app() -> Flask:
    return App().flask_app
