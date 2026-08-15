# -*- coding: utf-8 -*-
"""test: marks, pending queue, work_seconds summary, new endpoints"""
import sys, tempfile, os, datetime
sys.stdout.reconfigure(encoding='utf-8')

from backend.marks import MarksManager
from backend import storage

# ---- MarksManager ----
tmp = os.path.join(tempfile.mkdtemp(), "window_marks.json")
m = MarksManager(tmp)
m.add("title", "youtube", "休闲")
m.add("app", "vscode.exe", "科研")
assert m.find_category("msedge.exe", "youtube video")[0] == "休闲", m.find_category("msedge.exe", "youtube video")
assert m.find_category("vscode.exe", "main.py")[0] == "科研"
assert m.find_category("chrome.exe", "arXiv: 2501.001")[0] is None
# suggest_match
mt, mm = m.suggest_match("msedge.exe", "【视频】- YouTube 和另外 3 个页面 - 用户1 - Microsoft Edge")
assert mt == "title" and mm == "youtube", (mt, mm)
mt2, mm2 = m.suggest_match("Weixin.exe", "Weixin")
assert mt2 == "app" and mm2 == "Weixin.exe", (mt2, mm2)
print("[marks] PASS")

# ---- summary with marks (exclude idle, work_seconds) ----
d = "2026-08-15"
recs = [
    {"kind": "activity", "start": f"{d}T09:00:00", "end": f"{d}T09:30:00", "app": "vscode.exe", "title": "main.py", "duration": 1800},
    {"kind": "activity", "start": f"{d}T09:30:00", "end": f"{d}T09:45:00", "app": "msedge.exe", "title": "YouTube video", "duration": 900},
    {"kind": "activity", "start": f"{d}T09:45:00", "end": f"{d}T10:45:00", "app": "idle", "title": "（空闲）", "duration": 3600},
    {"kind": "activity", "start": f"{d}T10:45:00", "end": f"{d}T11:15:00", "app": "chrome.exe", "title": "arxiv paper 1", "duration": 1800},
]
s = storage.summarize_activities(recs, marks=m)
assert s["total_active_seconds"] == 4500, s  # 空闲3600被排除
assert s["work_seconds"] == 3600, s  # vscode 科研 + arxiv 未分类
assert s["category_breakdown"]["休闲"] == 900
assert s["category_breakdown"]["科研"] == 1800
assert s["category_breakdown"]["未分类"] == 1800
print("[summary] PASS:", s["total_active_seconds"], "active /", s["work_seconds"], "work")

# ---- monitor pending queue ----
from backend.monitor import ActivityMonitor
mon_dir = tempfile.mkdtemp()
mm = MarksManager(os.path.join(mon_dir, "marks.json"))
mon = ActivityMonitor(journal_dir=mon_dir, poll_interval=1, idle_threshold=86400, flush_interval=2, marks_manager=mm)
now = datetime.datetime.now()
mon._current = None
mon._maybe_queue_pending("msedge.exe", "YouTube 视频标题 和另外 2 个页面", now)
mon._maybe_queue_pending("msedge.exe", "YouTube 视频标题 和另外 2 个页面", now)  # dedupe
mon._maybe_queue_pending("vscode.exe", "main.py", now)  # 未分类也进队列
assert len(mon.pending_marks()) == 2, mon.pending_marks()
mark = mon.classify_pending(next(p["key"] for p in mon.pending_marks() if p["app"] == "msedge.exe"), "休闲")
assert mark and mark["match"] == "youtube", mark
assert len(mon.pending_marks()) == 1
print("[monitor-pending] PASS")
mon.stop()

# ---- server endpoints ----
from backend.server import App
app = App()
app.cfg["journal_dir"] = os.path.join(tempfile.mkdtemp(), "journal")
client = app.flask_app.test_client()

r = client.get("/api/marks").get_json()
assert r["ok"] and r["categories"] == ["科研", "项目", "音乐", "休闲"]
r = client.post("/api/marks", json={"match_type": "title", "match": "github", "category": "项目"}).get_json()
mid = r["mark"]["id"]
assert r["ok"]
r = client.patch(f"/api/marks/{mid}", json={"category": "科研"}).get_json()
assert r["mark"]["category"] == "科研"
r = client.get("/api/pending-marks").get_json()
assert "pending" in r
print("[server-marks] PASS")

print("[ALL TESTS PASSED]")
