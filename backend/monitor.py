"""
后台活动监控模块（Windows）

通过 Win32 API 获取当前前台窗口标题、所属进程名、空闲时间，
按时间线记录到 journal/activity/YYYY-MM-DD.jsonl 中。

数据行格式:
  {"kind": "activity", "start": "...", "end": "...", "app": "...", "title": "...", "duration": 秒}
  {"kind": "note",     "time": "...", "content": "手动补充的记录"}
"""

import ctypes
import datetime
import json
import os
import threading
import time

from ctypes import wintypes

try:
    import psutil
except ImportError:
    psutil = None

from .marks import MarksManager


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 显式声明参数类型，避免 64 位截断
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32.GetTickCount.restype = wintypes.DWORD


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _MonitorState:
    """当前活动段状态"""

    def __init__(self, app: str, title: str, start: datetime.datetime):
        self.app = app
        self.title = title
        self.start = start
        self.last_seen = start


class ActivityMonitor:
    def __init__(
        self,
        journal_dir: str,
        poll_interval: int = 5,
        idle_threshold: int = 180,
        flush_interval: int = 60,
        on_event=None,
        marks_manager=None,
    ):
        self.journal_dir = journal_dir
        self.poll_interval = max(1, int(poll_interval))
        self.idle_threshold = max(5, int(idle_threshold))
        self.flush_interval = max(10, int(flush_interval))
        self.on_event = on_event  # 可选回调: on_event(record)
        self.marks = marks_manager  # 可选: MarksManager，用于分类标记
        self._stop = threading.Event()
        self._thread = None
        self._current = None
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._pending = {}   # key -> {app, title, first_seen} 待分类窗口
        self._skipped = set()  # 本次会话用户选择"忽略"的 key

    # ---------- 公开接口 ----------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="activity-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._finalize_current()

    def add_note(self, content: str, when: datetime.datetime = None) -> dict:
        """手动添加一条记录，返回写入的记录"""
        when = when or datetime.datetime.now()
        record = {
            "kind": "note",
            "time": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "content": content,
        }
        self._append_to_day(when, record)
        if self.on_event:
            try:
                self.on_event(record)
            except Exception:
                pass
        return record

    # ---------- 待分类队列 ----------

    def _window_key(self, app, title) -> str:
        return f"{app}|{title}"

    def _maybe_queue_pending(self, app, title, now: datetime.datetime):
        """新窗口出现且未分类时，加入待分类队列"""
        if not self.marks or not app or app == "idle":
            return
        if self.marks.find_category(app, title)[0]:
            return
        key = self._window_key(app, title)
        if key in self._skipped:
            return
        if key not in self._pending:
            self._pending[key] = {
                "key": key,
                "app": app,
                "title": title,
                "first_seen": now.strftime("%Y-%m-%dT%H:%M:%S"),
            }

    def pending_marks(self) -> list:
        return list(self._pending.values())

    def classify_pending(self, key: str, category: str) -> dict:
        """用户对某个待分类窗口选择了类别：保存标记并移出队列"""
        item = self._pending.pop(key, None)
        if not item:
            return None
        match_type, match = self.marks.suggest_match(item["app"], item["title"])
        return self.marks.add(match_type, match, category,
                              note=f"来自窗口: {MarksManager.normalize_title(item['title'])}")

    def skip_pending(self, key: str) -> bool:
        if key in self._pending:
            del self._pending[key]
        self._skipped.add(key)
        return True

    # ---------- 内部实现 ----------

    def _run(self):
        # 启动时记录一条初始活动，避免长时间空窗
        initial = self._get_foreground()
        if initial:
            self._current = _MonitorState(*initial, datetime.datetime.now())
            self._maybe_queue_pending(*initial, datetime.datetime.now())
        while not self._stop.is_set():
            time.sleep(self.poll_interval)
            now = datetime.datetime.now()
            try:
                self._tick(now)
            except Exception:
                pass

    def _tick(self, now: datetime.datetime):
        if self._is_idle():
            front = ("idle", "（空闲）")
        else:
            front = self._get_foreground()

        if self._current:
            same = front and (front[0], front[1]) == (self._current.app, self._current.title)
            if not same:
                self._finalize_current(now=now)
        if front and not self._current:
            self._current = _MonitorState(*front, now)
            self._maybe_queue_pending(front[0], front[1], now)

        # 周期性刷新当前段的结束时间，防止崩溃丢失数据
        if time.monotonic() - self._last_flush >= self.flush_interval:
            self._last_flush = time.monotonic()
            self._flush_current(now)

    def _get_foreground(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindowVisible(hwnd):
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").strip()

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = self._process_name(pid.value)
        if not app and not title:
            return None
        return (app or "unknown", title or "（无标题）")

    @staticmethod
    def _process_name(pid: int) -> str:
        if not pid:
            return "unknown"
        if psutil is not None:
            try:
                return psutil.Process(pid).name() or "unknown"
            except Exception:
                return "unknown"
        return "unknown"

    def _is_idle(self) -> bool:
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not user32.GetLastInputInfo(ctypes.byref(lii)):
                return False
            tick = kernel32.GetTickCount()
            elapsed = (tick - lii.dwTime) / 1000.0
            return elapsed >= self.idle_threshold
        except Exception:
            return False

    def _finalize_current(self, now: datetime.datetime = None):
        with self._lock:
            cur = self._current
            if not cur:
                return
            now = now or datetime.datetime.now()
            end = now
            start = cur.start
            duration = max(0, int((end - start).total_seconds()))
            record = {
                "kind": "activity",
                "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
                "app": cur.app,
                "title": cur.title,
                "duration": duration,
            }
            self._current = None
            self._append_to_day(end, record)
            if self.on_event:
                try:
                    self.on_event(record)
                except Exception:
                    pass

    def _flush_current(self, now: datetime.datetime):
        """把当前活动段的 end 时间写到文件最后一行，防止崩溃丢失"""
        with self._lock:
            cur = self._current
            if not cur:
                return
            day = cur.start.strftime("%Y-%m-%d")
            path = self._activity_path(day)
            if not os.path.exists(path):
                return
            lines = self._read_lines(path)
            if not lines:
                return
            new_end = now.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                last = json.loads(lines[-1])
                if last.get("kind") == "activity" and last.get("app") == cur.app:
                    start_dt = datetime.datetime.fromisoformat(last["start"])
                    last["end"] = new_end
                    last["duration"] = max(0, int((now - start_dt).total_seconds()))
                    lines[-1] = json.dumps(last, ensure_ascii=False)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines) + "\n")
            except Exception:
                pass

    # ---------- 文件读写 ----------

    def _activity_path(self, date: str) -> str:
        # journal/activity/YYYY/MM/YYYY-MM-DD.jsonl
        y, m = date.split("-")[:2]
        return os.path.join(self.journal_dir, "activity", y, m, f"{date}.jsonl")

    def _read_lines(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().splitlines()

    def _append_to_day(self, when: datetime.datetime, record: dict):
        date = when.strftime("%Y-%m-%d")
        path = self._activity_path(date)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_idle_seconds() -> float:
    """供前端展示空闲时长"""
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        return (kernel32.GetTickCount() - lii.dwTime) / 1000.0
    except Exception:
        return 0.0
