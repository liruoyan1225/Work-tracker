"""
报告生成：把活动时间线 + 手动日记喂给 AI，生成日报/周报/月报。

只负责拼装 prompt 与调用 AIClient，不直接写文件。
"""

import datetime

from . import storage


def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}分{s}秒" if s else f"{m}分钟"
    h, m = divmod(m, 60)
    return f"{h}小时{m}分"


def _fmt_activities(records: list, max_items: int = 200) -> str:
    lines = []
    for r in records:
        if r.get("kind") == "note":
            lines.append(f"[笔记] {r.get('time','')} {r.get('content','')}")
        elif r.get("kind") == "activity":
            start = (r.get("start") or "")[11:16]
            end = (r.get("end") or "")[11:16]
            dur = _fmt_duration(r.get("duration") or 0)
            lines.append(f"{start}-{end} [{r.get('app','')}] {r.get('title','')}（{dur}）")
    if len(lines) > max_items:
        lines = lines[:max_items]
        lines.append("...（记录过多，已截断）")
    return "\n".join(lines) if lines else "（当天无自动记录）"


def _fmt_daily_journals(journal_dir: str, dates: list) -> str:
    parts = []
    for d in dates:
        content = storage.read_daily_journal(journal_dir, d)
        if content.strip():
            parts.append(f"===== {d} =====")
            parts.append(content.strip())
    return "\n\n".join(parts) if parts else "（无手动日记）"


_SYSTEM = (
    "你是一名严谨的科研工作者专属工作汇报助手。你会根据用户提供的"
    "「工作活动时间线」「手动日记」等真实素材，生成专业、结构清晰、结果导向的工作汇报。"
    "规则：\n"
    "1. 只基于提供素材撰写，不编造不存在的成果；\n"
    "2. 用精炼的职业化语言，把碎片记录升级为成果描述；\n"
    "3. 优先突出科研相关内容（论文、实验、代码、阅读、项目）；\n"
    "4. 输出 Markdown 格式，使用 ## 分节；\n"
    "5. 全部用中文回复。"
)


def _base_prompt(kind: str, title: str, activities_text: str, journal_text: str, extra_notes: str = "") -> list:
    user = (
        f"请根据以下素材生成{kind}：\n\n"
        f"【素材一：工作活动时间线】\n{activities_text}\n\n"
        f"【素材二：手动日记/复盘】\n{journal_text}\n"
    )
    if extra_notes:
        user += f"\n【额外要求】\n{extra_notes}\n"
    user += (
        f"\n请生成一份《{title}》，Markdown 格式，包含以下板块（可用 ## 分节）：\n"
        f"- 核心进展（突出成果与量化）\n- 具体完成事项\n- 遇到的问题与卡点\n"
        f"- 下一步计划\n"
    )
    if kind == "日报":
        user += "额外要求：开头用一句话概括今天最重要的一件事。\n"
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def generate_daily(ai, journal_dir: str, date: str, extra_notes: str = "") -> str:
    records = storage.load_activities(journal_dir, date)
    journal = storage.read_daily_journal(journal_dir, date)
    messages = _base_prompt(
        "日报",
        f"{date} 科研日报",
        _fmt_activities(records),
        journal or "（无手动日记）",
        extra_notes,
    )
    return ai.chat(messages)


def generate_weekly(ai, journal_dir: str, start: str, end: str, extra_notes: str = "") -> str:
    dates = storage.date_range(start, end)
    all_records = []
    for d in dates:
        all_records.extend(storage.load_activities(journal_dir, d))
    summary = storage.summarize_activities(all_records)
    app_line = "，".join(
        f"{a['app']}（{_fmt_duration(a['seconds'])}）" for a in summary["app_top"][:8]
    ) or "（无）"

    activities_text = (
        f"时间范围：{start} 至 {end}\n"
        f"【应用使用 Top】{app_line}\n"
        f"【每日活动明细】\n" + "\n\n".join(
            f"--- {d} ---\n" + _fmt_activities(storage.load_activities(journal_dir, d))
            for d in dates
        )
    )
    journal_text = _fmt_daily_journals(journal_dir, dates)
    messages = _base_prompt(
        "周报",
        f"{start} 至 {end} 科研周报",
        activities_text,
        journal_text,
        extra_notes,
    )
    return ai.chat(messages)


def generate_monthly(ai, journal_dir: str, month: str, extra_notes: str = "") -> str:
    """month: 'YYYY-MM'"""
    y, m = month.split("-")
    start = f"{y}-{m}-01"
    last_day = _last_day_of_month(int(y), int(m))
    end = f"{y}-{m}-{last_day:02d}"
    return generate_weekly(ai, journal_dir, start, end, extra_notes=extra_notes)


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1) - datetime.date(year, month, 1)).days
