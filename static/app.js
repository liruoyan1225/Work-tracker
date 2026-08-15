/* WorkTracker 前端逻辑 */
const API = "";
let CONFIG = null;
let currentReport = null;
let charts = {};

const $ = (id) => document.getElementById(id);

/* ---------------- 工具函数 ---------------- */

function fmtDuration(sec) {
  sec = parseInt(sec || 0, 10);
  if (sec <= 0) return "0秒";
  if (sec < 60) return sec + "秒";
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return (s ? m + "分" + s + "秒" : m + "分钟");
  return Math.floor(m / 60) + "小时" + (m % 60 ? m % 60 + "分" : "");
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  return res.json();
}

async function req(method, path, body) {
  return api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

async function post(path, body) {
  return req("POST", path, body);
}

const CAT_COLORS = {
  "科研": "#4c8dff",
  "项目": "#22d3ee",
  "音乐": "#c084fc",
  "休闲": "#f59e0b",
  "未分类": "#64748b",
};
let toastHidden = new Set();

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function thisMonth() {
  return today().slice(0, 7);
}

/* 简易 Markdown 渲染（预览够用） */
function renderMarkdown(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  let html = "";
  const lines = (md || "").split("\n");
  let inList = false, inCode = false, codeBuf = [];
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().startsWith("```")) {
      if (inCode) { html += `<pre><code>${esc(codeBuf.join("\n"))}</code></pre>`; codeBuf = []; inCode = false; }
      else { closeList(); inCode = true; }
      continue;
    }
    if (inCode) { codeBuf.push(line); continue; }
    if (line.trim() === "") { closeList(); continue; }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { closeList(); const lvl = h[1].length; html += `<h${lvl}>${esc(h[2])}</h${lvl}>`; continue; }
    if (/^[-*]\s+/.test(line.trim())) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${esc(line.trim().replace(/^[-*]\s+/, ""))}</li>`;
      continue;
    }
    if (/^\d+\.\s+/.test(line.trim())) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${esc(line.trim().replace(/^\d+\.\s+/, ""))}</li>`;
      continue;
    }
    closeList();
    let t = esc(line);
    t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
         .replace(/`(.+?)`/g, "<code>$1</code>");
    html += `<p>${t}</p>`;
  }
  closeList();
  return html;
}

/* ---------------- 标签切换 ---------------- */

function switchTab(tab) {
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  $("tab-" + tab).classList.add("active");
}

/* ---------------- 时间线 ---------------- */

async function loadTimeline(date) {
  $("tl-date").value = date;
  const data = await api("/api/activities?date=" + date);
  renderTimeline(data);
}

function renderTimeline(data) {
  const s = data.summary || {};
  $("kpi-active").textContent = fmtDuration(s.work_seconds);
  $("kpi-apps").textContent = (s.app_top || []).length;
  const notes = (data.records || []).filter(r => r.kind === "note");
  $("kpi-notes").textContent = notes.length;

  const acts = (data.records || []).filter(r => r.kind === "activity");
  let longest = 0;
  acts.forEach(a => { if ((a.duration || 0) > longest) longest = a.duration; });
  $("kpi-focus").textContent = longest ? fmtDuration(longest) : "--";

  const list = $("timeline-list");
  if (!data.records || data.records.length === 0) {
    list.innerHTML = `<div class="empty">这一天还没有记录。<br>点击「快速记一条」添加手动记录，或确保后台监控已开启。</div>`;
  } else {
    list.innerHTML = data.records.map(r => {
      if (r.kind === "note") {
        return `<div class="tl-item note">
          <div class="tl-time">${(r.time || "").slice(11, 16)}</div>
          <div class="tl-body"><span class="tl-note-text">📌 ${esc(r.content)}</span></div>
          <div class="tl-dur">手动</div>
        </div>`;
      }
      return `<div class="tl-item">
        <div class="tl-time">${(r.start || "").slice(11, 16)} - ${(r.end || "").slice(11, 16)}</div>
        <div class="tl-body">
          <span class="tl-app">${esc(r.app || "")}</span>
          <div class="tl-title">${esc(r.title || "")}</div>
        </div>
        <div class="tl-dur">${fmtDuration(r.duration)}</div>
      </div>`;
    }).join("");
  }

  const bars = $("app-bars");
  const top = (s.app_top || []).slice(0, 12);
  if (!top.length) { bars.innerHTML = `<div class="empty">暂无应用数据</div>`; return; }
  const max = top[0].seconds;
  bars.innerHTML = top.map((a, i) => {
    const pct = Math.max(2, Math.round(a.seconds / max * 100));
    return `<div class="app-bar-row">
      <div class="app-bar-name" title="${esc(a.app)}">${i + 1}. ${esc(a.app)}</div>
      <div class="app-bar-track"><div class="app-bar-fill" style="width:${pct}%"></div></div>
      <div class="app-bar-val">${fmtDuration(a.seconds)}</div>
    </div>`;
  }).join("");
}

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* ---------------- 统计 ---------------- */

function makeChart(id, type, labels, data, color, opts = {}) {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id);
  if (!ctx) return;
  charts[id] = new Chart(ctx, {
    type,
    data: { labels, datasets: [{ data, backgroundColor: color, borderColor: color, borderWidth: 1, borderRadius: 4 }] },
    options: Object.assign({
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "#232c40" }, ticks: { color: "#8a93a6" } },
        x: { grid: { display: false }, ticks: { color: "#8a93a6", maxRotation: 0 } },
      },
      color: "#8a93a6",
    }, opts),
  });
}

async function loadStats(date) {
  $("st-date").value = date;
  const data = await api("/api/activities?date=" + date);
  const s = data.summary || {};

  $("st-work").textContent = fmtDuration(s.work_seconds);
  $("st-active").textContent = fmtDuration(s.total_active_seconds);
  const cat = s.category_breakdown || {};
  $("st-fun").textContent = fmtDuration((cat["音乐"] || 0) + (cat["休闲"] || 0));
  $("st-unmarked").textContent = fmtDuration(cat["未分类"] || 0);

  const hours = (s.hourly || []).map(h => h.seconds);
  makeChart("chart-hourly", "bar", hours.map((_, i) => i + "时"), hours,
    Array.from({ length: 24 }, (_, i) => (i >= 9 && i <= 18) ? "#4c8dff" : "#2b3448"));

  renderCatBar(cat);
  renderAppUsage(s.app_top || []);

  // 本周整体
  const monday = getMonday(date);
  const sunday = addDays(monday, 6);
  const wk = await api(`/api/stats/range?start=${monday}&end=${sunday}`);
  if (wk.ok) {
    $("wk-days").textContent = wk.day_count;
    $("wk-total").textContent = fmtDuration(wk.summary.total_active_seconds);
    $("wk-top").textContent = (wk.summary.app_top[0] || {}).app || "--";
    const days = (wk.days || []).map(d => d.date);
    makeChart("chart-week", "bar", days, (wk.days || []).map(d => d.work_seconds), "#22d3ee");
  }
}

function renderCatBar(cat) {
  const order = ["科研", "项目", "音乐", "休闲", "未分类"];
  const total = order.reduce((a, k) => a + (cat[k] || 0), 0);
  const el = $("cat-bar");
  if (!total) { el.innerHTML = `<div class="empty">暂无数据</div>`; return; }
  el.innerHTML = order.filter(k => cat[k]).map(k => {
    const pct = Math.round(cat[k] / total * 100);
    return `<div class="cat-bar-row">
      <div class="cat-bar-name">${k}</div>
      <div class="cat-bar-track">
        <div class="cat-bar-fill" style="width:${pct}%;background:${CAT_COLORS[k]}"></div>
      </div>
      <div class="cat-bar-val">${fmtDuration(cat[k])} · ${pct}%</div>
    </div>`;
  }).join("");
}

function appColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360}, 58%, 55%)`;
}

function renderAppUsage(top) {
  const el = $("app-usage-list");
  if (!top.length) { el.innerHTML = `<div class="empty">暂无数据</div>`; return; }
  const total = top.reduce((a, x) => a + x.seconds, 0) || 1;
  const max = top[0].seconds || 1;
  el.innerHTML = top.map((a, i) => {
    const pct = Math.round(a.seconds / total * 100);
    const w = Math.max(2, Math.round(a.seconds / max * 100));
    const c = appColor(a.app);
    return `<div class="au-row">
      <div class="au-avatar" style="background:${c}">${esc((a.app || "?").charAt(0).toUpperCase())}</div>
      <div class="au-main">
        <div class="au-name">${i + 1}. ${esc(a.app)}</div>
        <div class="au-track"><div class="au-fill" style="width:${w}%"></div></div>
      </div>
      <div class="au-meta">${fmtDuration(a.seconds)} <span class="pct">${pct}%</span></div>
    </div>`;
  }).join("");
}

function getMonday(dateStr) {
  const d = new Date(dateStr);
  const day = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}
function addDays(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

/* ---------------- 报告 ---------------- */

let reportKind = "日报";
function switchReportKind(kind) {
  reportKind = kind;
  document.querySelectorAll(".type-btn").forEach(b => b.classList.toggle("active", b.dataset.kind === kind));
  $("opt-date-label").style.display = kind === "日报" ? "flex" : "none";
  $("opt-week-label").style.display = kind === "周报" ? "flex" : "none";
  $("opt-month-label").style.display = kind === "月报" ? "flex" : "none";
}

async function generateReport() {
  $("rep-error").style.display = "none";
  $("rep-loading").style.display = "block";
  $("rep-save").disabled = true;
  const body = { kind: reportKind, extra_notes: $("rep-extra").value.trim() };
  if (reportKind === "日报") body.date = $("rep-date").value || today();
  else if (reportKind === "周报") { body.start = $("rep-wstart").value; body.end = $("rep-wend").value; }
  else body.month = $("rep-month").value || thisMonth();
  const res = await post("/api/generate", body);
  $("rep-loading").style.display = "none";
  if (res.ok) {
    currentReport = res;
    $("rep-title").textContent = res.title;
    $("rep-content").innerHTML = renderMarkdown(res.content);
    $("rep-preview-card").style.display = "block";
    $("rep-save").disabled = false;
  } else {
    $("rep-error").textContent = res.error || "生成失败";
    $("rep-error").style.display = "block";
  }
}

async function saveReport() {
  if (!currentReport) return;
  const body = { kind: currentReport.kind, content: currentReport.content };
  if (currentReport.kind === "日报") body.date = $("rep-date").value || today();
  else if (currentReport.kind === "周报") body.date = $("rep-wstart").value || today();
  else { body.date = $("rep-month").value || thisMonth(); body.month = body.date; }
  const res = await post("/api/save-report", body);
  if (res.ok) { alert("已保存到：" + res.path); loadReports(); }
  else alert("保存失败：" + (res.error || ""));
}

async function loadReports() {
  const res = await api("/api/reports");
  const list = $("rep-list");
  if (!res.reports.length) { list.innerHTML = `<div class="empty">暂无报告</div>`; return; }
  list.innerHTML = res.reports.map(r =>
    `<div class="report-item">
      <span class="name">${esc(r.name)}</span>
      <button class="view" data-path="${esc(r.path)}">查看</button>
    </div>`).join("");
  list.querySelectorAll(".view").forEach(b => b.onclick = () => viewReport(b.dataset.path));
}

async function viewReport(path) {
  const res = await api("/api/report?path=" + encodeURIComponent(path));
  if (res.ok) {
    currentReport = null;
    $("rep-title").textContent = res.name;
    $("rep-content").innerHTML = renderMarkdown(res.content);
    $("rep-preview-card").style.display = "block";
    $("rep-save").disabled = true;
  }
}

/* ---------------- 日记 ---------------- */

async function loadJournal(date) {
  $("jn-date").value = date;
  const res = await api("/api/activities?date=" + date);
  $("jn-editor").value = res.journal || "";
}

async function appendJournal() {
  const content = $("jn-append-text").value.trim();
  if (!content) return;
  const res = await post("/api/journal/append", {
    date: $("jn-date").value || today(),
    section: $("jn-section").value,
    content,
  });
  if (res.ok) { $("jn-append-text").value = ""; await loadJournal($("jn-date").value); }
  else alert("追加失败");
}

async function saveJournal() {
  const res = await post("/api/journal/save", {
    date: $("jn-date").value || today(),
    content: $("jn-editor").value,
  });
  if (res.ok) alert("日记已保存：" + res.path);
  else alert("保存失败");
}

/* ---------------- 设置 ---------------- */

async function loadConfig() {
  CONFIG = await api("/api/config");
  $("set-journal").value = CONFIG.journal_dir || "";
  $("set-baseurl").value = CONFIG.ai.base_url || "";
  $("set-apikey").value = CONFIG.ai.api_key || "";
  $("set-model").value = CONFIG.ai.model || "";
  $("set-temperature").value = CONFIG.ai.temperature ?? 0.7;
  $("set-ai-enabled").checked = !!CONFIG.ai.enabled;
  $("set-monitor-enabled").checked = !!CONFIG.monitor.enabled;
  $("set-poll").value = CONFIG.monitor.poll_interval || 5;
  $("set-idle").value = CONFIG.monitor.idle_threshold || 180;

  const sel = $("set-provider");
  sel.innerHTML = '<option value="">自定义…</option>';
  (CONFIG.providers || []).forEach(p => {
    const o = document.createElement("option");
    o.value = JSON.stringify({ base_url: p.base_url, model: p.model, models: p.models || [] });
    o.textContent = p.label;
    sel.appendChild(o);
  });
  // 根据已保存的 base_url 匹配服务商，填充该服务的模型列表
  const saved = (CONFIG.providers || []).find(p => CONFIG.ai.base_url === p.base_url);
  fillModelPresets(saved ? saved.models : []);
}

function fillModelPresets(models) {
  const sel = $("set-model-preset");
  sel.innerHTML = '<option value="">从列表选择模型…</option>';
  (models || []).forEach(m => {
    const o = document.createElement("option");
    o.value = m;
    o.textContent = m;
    sel.appendChild(o);
  });
}

function onProviderChange() {
  const val = $("set-provider").value;
  if (!val) return;
  const p = JSON.parse(val);
  $("set-baseurl").value = p.base_url;
  $("set-model").value = p.model;
  fillModelPresets(p.models);
}

async function testAI() {
  const btn = $("set-ai-test");
  btn.disabled = true; btn.textContent = "测试中…";
  const res = await post("/api/ai/test", {
    base_url: $("set-baseurl").value.trim(),
    api_key: $("set-apikey").value.trim(),
    model: $("set-model").value.trim(),
  });
  btn.disabled = false; btn.textContent = "测试连接";
  const el = $("set-ai-result");
  if (res.ok) { el.style.color = "var(--ok)"; el.textContent = "✅ 连接成功，AI 回复：" + res.reply; }
  else { el.style.color = "var(--err)"; el.textContent = "❌ " + res.error; }
}

async function saveSettings() {
  const res = await post("/api/config", {
    journal_dir: $("set-journal").value.trim(),
    ai: {
      enabled: $("set-ai-enabled").checked,
      base_url: $("set-baseurl").value.trim(),
      api_key: $("set-apikey").value.trim(),
      model: $("set-model").value.trim(),
      temperature: parseFloat($("set-temperature").value) || 0.7,
    },
    monitor: {
      enabled: $("set-monitor-enabled").checked,
      poll_interval: parseInt($("set-poll").value) || 5,
      idle_threshold: parseInt($("set-idle").value) || 180,
    },
  });
  if (res.ok) {
    const tip = $("set-saved"); tip.style.display = "inline";
    setTimeout(() => tip.style.display = "none", 2000);
    refreshMonitorStatus();
  } else alert("保存失败");
}

/* ---------------- 窗口标记 ---------------- */

async function loadMarks() {
  const res = await api("/api/marks");
  renderMarksList(res.marks || []);
}

function renderMarksList(marks) {
  const el = $("marks-list");
  if (!marks.length) { el.innerHTML = `<div class="empty">暂无标记，可在上方添加</div>`; return; }
  el.innerHTML = marks.map(m => `
    <div class="mark-item" data-id="${esc(m.id)}">
      <span class="mark-type">${m.match_type === "app" ? "应用名=" : "标题含"}</span>
      <span class="mark-match" title="${esc(m.match)}">${esc(m.match)}</span>
      <select class="mark-cat" data-id="${esc(m.id)}">
        ${["科研", "项目", "音乐", "休闲"].map(c => `<option value="${c}" ${m.category === c ? "selected" : ""}>${c}</option>`).join("")}
      </select>
      <button class="mark-del" data-id="${esc(m.id)}">删除</button>
    </div>`).join("");
  el.querySelectorAll(".mark-cat").forEach(sel => sel.onchange = async () => {
    await req("PATCH", `/api/marks/${sel.dataset.id}`, { category: sel.value });
  });
  el.querySelectorAll(".mark-del").forEach(btn => btn.onclick = async () => {
    await api(`/api/marks/${btn.dataset.id}`, { method: "DELETE" });
    loadMarks();
  });
}

async function loadPending() {
  const res = await api("/api/pending-marks");
  const pending = res.pending || [];
  renderPendingInTab(pending);
  renderClassifyToast(pending);
}

function pendingButtonsHtml(p, withIgnore = true) {
  const cats = ["科研", "项目", "音乐", "休闲"]
    .map(c => `<button class="cat-btn c-${c}" data-key="${esc(p.key)}" data-cat="${c}">${c}</button>`).join("");
  const skip = withIgnore ? `<button class="cat-btn skip" data-key="${esc(p.key)}" data-skip="1">忽略</button>` : "";
  return cats + skip;
}

function bindPendingButtons(container, onDone) {
  container.querySelectorAll(".cat-btn").forEach(b => b.onclick = async () => {
    if (b.dataset.skip) await post("/api/pending-marks/skip", { key: b.dataset.key });
    else await post("/api/pending-marks/classify", { key: b.dataset.key, category: b.dataset.cat });
    toastHidden.delete(b.dataset.key);
    loadPending();
    loadMarks();
    if (onDone) onDone();
  });
}

function renderPendingInTab(pending) {
  const el = $("pending-list");
  if (!pending.length) { el.innerHTML = `<div class="empty">暂无待分类窗口</div>`; return; }
  el.innerHTML = pending.map(p => `
    <div class="pending-item">
      <div class="pending-info">
        <div class="pending-app">${esc(p.app)}</div>
        <div class="pending-title" title="${esc(p.title)}">${esc(p.title)}</div>
      </div>
      <div class="pending-actions">${pendingButtonsHtml(p)}</div>
    </div>`).join("");
  bindPendingButtons(el);
}

function renderClassifyToast(pending) {
  const visible = pending.filter(p => !toastHidden.has(p.key));
  const toast = $("classify-toast");
  if (!visible.length) { toast.style.display = "none"; return; }
  toast.style.display = "block";
  $("ct-body").innerHTML = visible.map(p => `
    <div class="ct-item">
      <div class="ct-title"><span class="ct-app">${esc(p.app)}</span>${esc(p.title)}</div>
      <div class="ct-actions">${pendingButtonsHtml(p)}</div>
    </div>`).join("");
  bindPendingButtons($("ct-body"), () => loadStats($("st-date").value || today()));
}

/* ---------------- 监控状态与时钟 ---------------- */

async function refreshMonitorStatus() {
  try {
    const res = await api("/api/status");
    const el = $("monitor-status");
    if (res.monitor_running) { el.classList.remove("off"); el.innerHTML = '<span class="dot"></span> 后台监控中'; }
    else { el.classList.add("off"); el.innerHTML = '<span class="dot"></span> 监控已停止'; }
  } catch (e) { /* 服务未就绪 */ }
}

function tickClock() {
  const d = new Date();
  $("clock").textContent = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/* ---------------- 事件绑定 ---------------- */

function bind() {
  document.querySelectorAll(".nav-item").forEach(b => b.onclick = () => switchTab(b.dataset.tab));

  // 时间线
  $("tl-date").onchange = () => loadTimeline($("tl-date").value);
  $("tl-prev").onclick = () => loadTimeline(addDays($("tl-date").value || today(), -1));
  $("tl-next").onclick = () => loadTimeline(addDays($("tl-date").value || today(), 1));
  $("tl-today").onclick = () => loadTimeline(today());
  $("quick-note-btn").onclick = async () => {
    const content = $("quick-note").value.trim();
    if (!content) return;
    const res = await post("/api/notes", { content, date: $("tl-date").value });
    if (res.ok) { $("quick-note").value = ""; await loadTimeline($("tl-date").value); }
  };
  $("quick-note").addEventListener("keydown", e => { if (e.key === "Enter") $("quick-note-btn").click(); });

  // 统计
  $("st-load").onclick = () => loadStats($("st-date").value);

  // 报告
  document.querySelectorAll(".type-btn").forEach(b => b.onclick = () => switchReportKind(b.dataset.kind));
  $("rep-generate").onclick = generateReport;
  $("rep-save").onclick = saveReport;

  // 日记
  $("jn-load").onclick = () => loadJournal($("jn-date").value);
  $("jn-append-btn").onclick = appendJournal;
  $("jn-save").onclick = saveJournal;

  // 设置
  $("set-provider").onchange = onProviderChange;
  $("set-model-preset").onchange = () => {
    const v = $("set-model-preset").value;
    if (v) $("set-model").value = v;
  };
  $("set-ai-test").onclick = testAI;
  $("set-save").onclick = saveSettings;

  // 窗口标记
  $("mk-add").onclick = async () => {
    const match = $("mk-match").value.trim();
    if (!match) return;
    await post("/api/marks", { match_type: $("mk-type").value, match, category: $("mk-category").value });
    $("mk-match").value = "";
    loadMarks();
  };
  $("mk-match").addEventListener("keydown", e => { if (e.key === "Enter") $("mk-add").click(); });
  $("ct-close").onclick = () => {
    api("/api/pending-marks").then(res => (res.pending || []).forEach(p => toastHidden.add(p.key)));
    $("classify-toast").style.display = "none";
  };
}

/* ---------------- 启动 ---------------- */

(async function init() {
  bind();
  tickClock();
  setInterval(tickClock, 1000);
  setInterval(refreshMonitorStatus, 10000);
  const t = today();
  loadTimeline(t);
  loadStats(t);
  loadReports();
  loadJournal(t);
  loadConfig();
  refreshMonitorStatus();
  switchReportKind("日报");
  loadMarks();
  loadPending();
  setInterval(loadPending, 5000);
})();
