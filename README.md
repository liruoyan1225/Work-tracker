# WorkTracker · 科研工作记录助手

一个**本地优先**的桌面应用，自动记录你在电脑上的工作轨迹（前台窗口/应用 + 时间线 + 使用时长），
并用 AI 一键生成 **日报 / 周报 / 月报**，直接读写你的 Obsidian `journal` 目录。

> 灵感来自「小黑日报助手」。不同点：本工具**不做截图识别**，只记录窗口标题与使用时长，隐私更轻；
> 数据完全存本地 markdown/jsonl，与你的 Obsidian 日志体系打通。

---

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 🕐 自动时间线 | 后台静默记录前台窗口切换、应用名、起止时间、时长，按天存为 `journal/activity/YYYY/MM/YYYY-MM-DD.jsonl` |
| 📝 手动记录 | 随时快速记一条（写论文、跑实验、开会…），与自动记录合并展示 |
| 📊 统计 | 每天的有效时长、应用使用排行、每小时活跃分布、本周汇总 |
| 🤖 AI 报告 | 基于真实时间线 + 你的日记，一键生成日报/周报/月报，可自定义模板要求 |
| 📔 日记打通 | 直接读写 `journal/YYYY-MM-DD.md`，可在软件里编辑、快速追加到指定板块 |
| 🖥️ 桌面应用 | 独立窗口（pywebview），也可 `--browser` 在浏览器打开 |
| 🔒 本地优先 | 数据全在本机，AI 只发送「活动时间线 + 日记文本」用于生成报告，不做截图 |

---

## 🚀 快速开始

### 环境要求
- Windows 10/11
- Python 3.10+（已安装 3.13 可直接用）
- 可选：WebView2 运行时（Win10/11 一般自带，pywebview 用）

### 运行

```bat
start.bat
```

或手动：

```bat
pip install -r requirements.txt
python main.py          :: 桌面窗口模式
python main.py --browser :: 浏览器模式（不弹窗口）
```

首次打开后：**设置 → 填写 AI 配置 → 保存**，即可一键生成报告。

---

## 🤖 AI 配置（设置 → AI 配置）

支持所有 **OpenAI 兼容** 接口，下拉可快速选择：

| 服务商 | API 地址 | 模型 | 备注 |
|--------|----------|------|------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 国内直连、便宜，推荐 |
| OpenAI (GPT) | `https://api.openai.com/v1` | `gpt-4o-mini` | 需要自己的 API Key |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | 完全离线 |

> ⚠️ **没有免费的 GPT API**：OpenAI 的「免费额度」指 ChatGPT 网页版，不适用于 API 调用。
> 请在对应平台官网注册获取你自己的 API Key（DeepSeek 注册即送少量体验额度，且按量计费非常便宜）。

填好后点「测试连接」验证，通过后勾选「启用 AI 生成」。

---

## 📁 数据存储

```
journal/                          ← 你的 Obsidian 日志目录（可在设置里改）
├── YYYY-MM-DD.md                 ← 手动日记（沿用你现有的复盘模板）
├── activity/
│   └── YYYY/MM/YYYY-MM-DD.jsonl  ← 自动记录的活动时间线（jsonl 文本）
└── reports/
    ├── 日报-YYYY-MM-DD.md
    ├── 周报-YYYY-MM-WW.md
    └── 月报-YYYY-MM.md
```

- `data/config.json` 保存设置（含 API Key，已加入 `.gitignore`，**不会上传**）。

---

## 🛠️ 开发

```
backend/
├── config.py     # 配置读写
├── monitor.py    # 后台窗口监控（Win32 API，不做截图）
├── storage.py    # journal / 活动 / 报告 读写
├── ai.py         # OpenAI 兼容 AI 客户端
├── reporter.py   # 日报/周报/月报 prompt 与生成
└── server.py     # Flask 本地 API
static/           # Web 前端（时间线/统计/报告/日记/设置）
main.py           # 入口：桌面窗口 + 服务 + 监控
test_smoke.py     # 冒烟测试（可选）
```

### 主要接口
- `GET  /api/activities?date=YYYY-MM-DD` 某天时间线 + 统计
- `POST /api/generate` 生成报告 `{kind: 日报|周报|月报, ...}`
- `POST /api/save-report` 保存到 `journal/reports/`
- `POST /api/notes` 手动记录
- `GET/POST /api/config` 读取/保存设置

---

## 🔒 隐私说明

- 只记录「窗口标题 + 应用名 + 时间」，**不采集截图、按键、剪贴板**。
- 所有数据保存在你本机，可随时删除 `activity/` 目录。
- AI 生成时，会把你当天的时间线与日记文本发送给所选服务商；介意可用本地 Ollama。
- 浏览器窗口标题可能包含页面信息，属于正常记录范围；如需更严格，可在后续版本加「排除敏感应用」白名单。

---

## 📜 许可证
MIT
