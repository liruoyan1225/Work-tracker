"""
数据存储模块：读写 journal 目录下的日记、活动记录、报告。

目录结构:
  journal/
    YYYY-MM-DD.md                 # 手动日记（你现有的格式）
    activity/
      YYYY/
        MM/
          YYYY-MM-DD.jsonl        # 活动时间线
    reports/
      日报-YYYY-MM-DD.md          # AI 生成的报告
      周报-YYYY-MM-DD.md
      月报-YYYY-MM.md
"""

import datetime
import glob
import json
import os
import re


def parse_date(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def date_str(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


# ---------- 活动记录 ----------

def activity_path(journal_dir: str, date: str) -> str:
    y, m = date.split("-")[:2]
    return os.path.join(journal_dir, "activity", y, m, f"{date}.jsonl")


def load_activities(journal_dir: str, date: str) -> list:
    """读取某天的活动记录（活动 + 笔记），按时间排序"""
    path = activity_path(journal_dir, date)
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    records.sort(key=lambda r: r.get("start") or r.get("time") or "")
    return records


def list_activity_dates(journal_dir: str) -> list:
    """列出所有有活动记录的日期，倒序"""
    dates = set()
    base = os.path.join(journal_dir, "activity")
    for f in glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True):
        name = os.path.basename(f)
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.jsonl$", name)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


def append_activity(journal_dir: str, date: str, record: dict) -> str:
    path = activity_path(journal_dir, date)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


# ---------- 手动日记 ----------

def daily_journal_path(journal_dir: str, date: str) -> str:
    return os.path.join(journal_dir, f"{date}.md")


def read_daily_journal(journal_dir: str, date: str) -> str:
    path = daily_journal_path(journal_dir, date)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def list_journal_dates(journal_dir: str) -> list:
    dates = set()
    for f in glob.glob(os.path.join(journal_dir, "*.md")):
        name = os.path.basename(f)
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.md$", name)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


def all_available_dates(journal_dir: str) -> list:
    """活动记录 + 手动日记的日期并集"""
    dates = set(list_activity_dates(journal_dir))
    dates.update(list_journal_dates(journal_dir))
    return sorted(dates, reverse=True)


# ---------- 报告 ----------

def report_path(journal_dir: str, kind: str, date: str) -> str:
    if kind == "日报":
        name = f"日报-{date}.md"
    elif kind == "周报":
        week_start = _week_start(date)
        name = f"周报-{week_start}.md"
    elif kind == "月报":
        month = date[:7]
        name = f"月报-{month}.md"
    else:
        name = f"报告-{date}.md"
    return os.path.join(journal_dir, "reports", name)


def _week_start(date: str) -> str:
    d = parse_date(date)
    return date_str(d - datetime.timedelta(days=d.weekday()))


def save_report(journal_dir: str, kind: str, date: str, content: str) -> str:
    path = report_path(journal_dir, kind, date)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def list_reports(journal_dir: str) -> list:
    reports = []
    base = os.path.join(journal_dir, "reports")
    if not os.path.isdir(base):
        return reports
    for f in sorted(glob.glob(os.path.join(base, "*.md")), reverse=True):
        reports.append({
            "path": f,
            "name": os.path.basename(f),
        })
    return reports


# ---------- 聚合统计 ----------

def summarize_activities(records: list, marks=None, work_categories=None) -> dict:
    """把活动记录聚合为: 应用时长 Top、总活跃时长、有效工作时长、分类分布、按小时分布。

    - total_active_seconds : 非空闲总时长
    - work_seconds         : 有效工作时长 = 非空闲 且 类别∈(科研/项目) 或 未分类
    - category_breakdown   : {类别: 秒}
    """
    work_categories = work_categories or ["科研", "项目"]
    app_time = {}
    total_active = 0
    work_seconds = 0
    category_seconds = {}
    hourly = {}
    for r in records:
        if r.get("kind") != "activity":
            continue
        app = r.get("app", "unknown")
        title = r.get("title", "")
        duration = int(r.get("duration") or 0)
        if duration <= 0:
            continue
        if app == "idle":
            continue  # 空闲不算
        total_active += duration
        app_time[app] = app_time.get(app, 0) + duration

        cat = None
        if marks is not None:
            cat, _ = marks.find_category(app, title)
        label = cat if cat else "未分类"
        category_seconds[label] = category_seconds.get(label, 0) + duration
        if cat is None or cat in work_categories:
            work_seconds += duration

        start = r.get("start")
        if start:
            try:
                hh = int(datetime.datetime.fromisoformat(start).hour)
                hourly[str(hh).zfill(2)] = hourly.get(str(hh).zfill(2), 0) + duration
            except Exception:
                pass
    app_top = sorted(app_time.items(), key=lambda x: x[1], reverse=True)
    return {
        "total_active_seconds": total_active,
        "work_seconds": work_seconds,
        "category_breakdown": category_seconds,
        "app_top": [{"app": k, "seconds": v} for k, v in app_top],
        "hourly": [{"hour": h, "seconds": hourly.get(h, 0)} for h in [f"{i:02d}" for i in range(24)]],
    }


def date_range(start: str, end: str) -> list:
    d = parse_date(start)
    last = parse_date(end)
    out = []
    while d <= last:
        out.append(date_str(d))
        d += datetime.timedelta(days=1)
    return out


def activities_in_range(journal_dir: str, start: str, end: str) -> dict:
    """返回 {date: [records]} 的字典（闭区间）"""
    result = {}
    for d in date_range(start, end):
        records = load_activities(journal_dir, d)
        if records:
            result[d] = records
    return result
