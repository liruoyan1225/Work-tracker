"""
窗口分类标记管理：把"应用/窗口标题"映射到类别（科研/项目/音乐/休闲）。

数据存于 data/window_marks.json:
  [
    {"id": "...", "match_type": "app"|"title", "match": "msedge.exe"|"youtube",
     "category": "科研"|"项目"|"音乐"|"休闲", "note": "...", "created": 时间戳}
  ]

匹配规则：
  1) 应用名完全匹配（如 vscode.exe）
  2) 窗口标题包含关键字（如标题含 "YouTube" → 音乐/休闲）
"""

import json
import os
import time
import uuid

CATEGORIES = ["科研", "项目", "音乐", "休闲"]
# 有效工作 = 以下类别（未分类也暂算工作，避免一上来全部为 0）
WORK_CATEGORIES = ["科研", "项目"]

# 常见站点 → 用于从浏览器标题里提取"站点关键字"作为匹配词
SITE_KEYWORDS = [
    ("arxiv", "arxiv"), ("arXiv", "arxiv"), ("github", "github"), ("GitHub", "github"),
    ("bilibili", "bilibili"), ("哔哩哔哩", "bilibili"), ("YouTube", "youtube"),
    ("youtube", "youtube"), ("DeepSeek", "deepseek"), ("ChatGPT", "chatgpt"),
    ("openai", "openai"), ("IEEE", "ieee"), ("谷歌学术", "scholar"),
    ("Google Scholar", "scholar"), ("知网", "cnki"), ("CNKI", "cnki"),
    ("Springer", "springer"), ("nature", "nature"), ("百度", "baidu"),
    ("腾讯文档", "腾讯文档"), ("飞书", "feishu"), ("钉钉", "dingtalk"),
    ("Overleaf", "overleaf"), ("知云", "zhiyun"),
]

BROWSER_APPS = {"msedge.exe", "chrome.exe", "firefox.exe", "iexplore.exe", "brave.exe", "opera.exe", "360se.exe", "QQBrowser.exe"}


class MarksManager:
    def __init__(self, path: str):
        self.path = path
        self.marks = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.marks = data
            except Exception:
                self.marks = []

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.marks, f, ensure_ascii=False, indent=2)

    # ---------- 查询 ----------

    def find_category(self, app: str, title: str):
        """返回 (类别 or None, 命中的标记 or None)"""
        if not app:
            return None, None
        # 1) 应用名完全匹配
        for m in self.marks:
            if m.get("match_type") == "app" and m.get("match") and app.lower() == str(m["match"]).lower():
                return m.get("category"), m
        # 2) 标题包含关键字
        if title:
            tl = title.lower()
            for m in self.marks:
                if m.get("match_type") == "title" and m.get("match"):
                    if str(m["match"]).lower() in tl:
                        return m.get("category"), m
        return None, None

    # ---------- 增删改 ----------

    def add(self, match_type: str, match: str, category: str, note: str = "") -> dict:
        m = {
            "id": uuid.uuid4().hex[:10],
            "match_type": match_type if match_type in ("app", "title") else "title",
            "match": match.strip(),
            "category": category if category in CATEGORIES else CATEGORIES[0],
            "note": note,
            "created": int(time.time()),
        }
        self.marks.append(m)
        self._save()
        return m

    def update(self, mark_id: str, **kw) -> dict:
        for m in self.marks:
            if m.get("id") == mark_id:
                for k, v in kw.items():
                    if k in ("match_type", "match", "category", "note"):
                        m[k] = v
                self._save()
                return m
        return None

    def delete(self, mark_id: str) -> bool:
        before = len(self.marks)
        self.marks = [m for m in self.marks if m.get("id") != mark_id]
        if len(self.marks) != before:
            self._save()
            return True
        return False

    def all(self) -> list:
        return self.marks

    # ---------- 工具 ----------

    @staticmethod
    def suggest_match(app: str, title: str) -> tuple:
        """根据窗口自动建议 (match_type, match)"""
        if app and app.lower() in {b.lower() for b in BROWSER_APPS}:
            if title:
                for kw, slug in SITE_KEYWORDS:
                    if kw.lower() in title.lower():
                        return ("title", slug)
                # 取标题主片段（去掉 "和另外 N 个页面" 尾部）
                main = title.split("和另外")[0].strip()
                main = main.split(" - ")[0].strip()
                if main:
                    return ("title", main[:40])
            return ("app", app)
        return ("app", app)

    @staticmethod
    def normalize_title(title: str) -> str:
        """去掉浏览器标题中的“和另外 N 个页面”等噪声，作为待标记的展示名"""
        t = title or ""
        t = t.split("和另外")[0].strip()
        t = t.split(" - ")[0].strip()
        return t[:60]
