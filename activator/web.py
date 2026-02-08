"""
Awakener - Observer Dashboard
Lightweight web interface to watch the agent's activity.
"""

import json
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn


app = FastAPI(title="Awakener Observer")

# Will be set by start_dashboard()
_state = None


# ── API Endpoints ─────────────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    """Current activator status."""
    return JSONResponse(_state.to_dict())


@app.get("/api/notebook")
def api_notebook():
    """Current notebook content."""
    try:
        with open(_state.notebook_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "(笔记本尚未创建)"
    return JSONResponse({"content": content})


@app.get("/api/timeline")
def api_timeline():
    """All timeline records."""
    records = []
    try:
        with open(_state.timeline_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass
    # Return newest first
    records.reverse()
    return JSONResponse(records)


@app.get("/api/logs")
def api_logs():
    """Last N lines of activator log. Always reads the latest log file."""
    try:
        log_dir = os.path.dirname(_state.log_path)
        
        # Find the latest log file
        log_files = [f for f in os.listdir(log_dir) if f.startswith("activator-") and f.endswith(".log")]
        if not log_files:
            return JSONResponse({"lines": []})
        
        latest_log = os.path.join(log_dir, sorted(log_files)[-1])
        
        with open(latest_log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        # Return last 300 lines
        tail = lines[-300:] if len(lines) > 300 else lines
        return JSONResponse({"lines": [l.rstrip() for l in tail]})
    except Exception as e:
        return JSONResponse({"lines": [], "error": str(e)})


# ── Main Page ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    """Observer dashboard - single page."""
    return DASHBOARD_HTML


# ── Dashboard HTML ────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Awakener Observer</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Courier New', monospace;
    background: #0a0a0a; color: #e0e0e0;
    min-height: 100vh;
  }
  .header {
    background: #111; border-bottom: 1px solid #333;
    padding: 16px 24px; display: flex; align-items: center; gap: 16px;
  }
  .header h1 { font-size: 18px; color: #4fc3f7; }
  .status-dot {
    width: 10px; height: 10px; border-radius: 50%;
    display: inline-block; margin-right: 6px;
  }
  .status-dot.running { background: #4caf50; animation: pulse 1s infinite; }
  .status-dot.waiting { background: #ff9800; }
  .status-dot.stopped { background: #f44336; }
  .status-dot.starting { background: #9e9e9e; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  /* Main container: three columns with fixed center width */
  .main-container {
    display: grid;
    grid-template-columns: minmax(350px, 1fr) 850px minmax(400px, 1fr);
    gap: 16px;
    padding: 16px;
    height: calc(100vh - 90px);
    max-width: 2400px;
    margin: 0 auto;
  }
  @media (max-width: 1800px) {
    .main-container {
      grid-template-columns: 350px 800px 400px;
    }
  }
  @media (max-width: 1600px) {
    .main-container {
      grid-template-columns: 320px 750px 380px;
    }
  }
  @media (max-width: 1400px) {
    .main-container {
      grid-template-columns: 300px 700px 350px;
    }
  }
  @media (max-width: 1024px) {
    .main-container {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr auto;
    }
  }

  /* Card styles */
  .info-card, .log-card, .notebook-card {
    background: #151515;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .card-header {
    background: #1a1a1a;
    padding: 12px 16px;
    border-bottom: 1px solid #2a2a2a;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 14px;
    color: #4fc3f7;
    font-weight: bold;
    flex-shrink: 0;
  }

  .card-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .log-info {
    color: #888;
    font-size: 12px;
    font-weight: normal;
  }

  .status-badge {
    font-size: 12px;
    font-weight: normal;
  }

  /* Notebook content */
  .notebook-content {
    white-space: pre-wrap;
    font-size: 13px;
    line-height: 1.6;
    color: #c8e6c9;
    font-family: 'Courier New', monospace;
  }

  /* Info card content */
  .info-section {
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #2a2a2a;
  }
  .info-section:last-child {
    border-bottom: none;
  }
  .info-section h3 {
    font-size: 13px;
    color: #4fc3f7;
    margin-bottom: 10px;
  }
  .info-section p {
    font-size: 12px;
    color: #aaa;
    line-height: 1.6;
    margin-bottom: 8px;
  }
  .config-item {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 12px;
    border-bottom: 1px solid #1a1a1a;
  }
  .config-item:last-child {
    border-bottom: none;
  }
  .config-label {
    color: #888;
  }
  .config-value {
    color: #e0e0e0;
    font-weight: bold;
  }

  /* Round styles */
  .log-round {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 2px solid #2a2a2a;
  }
  .log-round:last-child {
    border-bottom: none;
  }
  .round-title {
    color: #4fc3f7;
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 12px;
    padding: 6px 0;
  }

  /* Text blocks (reasoning & output) - white, large font */
  .text-block {
    color: #e8e8e8;
    font-size: 14px;
    line-height: 1.7;
    margin-bottom: 10px;
    padding: 8px 0;
    white-space: pre-wrap;
  }

  /* Tool blocks (collapsible) */
  .tool-block {
    margin: 8px 0;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    background: #1a1a1a;
  }
  .tool-toggle {
    padding: 8px 12px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #ffb74d;
    font-size: 12px;
  }
  .tool-toggle:hover { background: #222; }
  .toggle-arrow {
    color: #666;
    font-size: 11px;
  }
  .tool-content {
    padding: 10px 12px;
    border-top: 1px solid #2a2a2a;
    background: #0f0f0f;
  }
  .tool-content.collapsed { display: none; }
  .tool-call-full {
    color: #ffa726;
    font-size: 12px;
    margin-bottom: 8px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1a1a1a;
  }
  .tool-result-text {
    color: #81c784;
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    max-height: 300px;
    overflow-y: auto;
  }

  /* Round status */
  .round-status {
    margin-top: 10px;
    padding: 6px 10px;
    font-size: 11px;
    border-radius: 3px;
    background: #1a1a1a;
    color: #888;
  }

  @media (max-width: 768px) {
    .container { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<div class="header">
  <h1>&#x1f441; Awakener Observer</h1>
  <span id="statusBadge"><span class="status-dot starting"></span>Starting</span>
  <span style="margin-left:auto; color:#555; font-size:12px;" id="autoRefresh">Auto-refresh: 5s</span>
</div>

<div class="main-container">
  <!-- Left: Project Info & Config -->
  <div class="info-card">
    <div class="card-header">
      <span>ℹ️ Project Info</span>
    </div>
    <div class="card-body" id="infoPanel">
      <div class="info-section">
        <h3>AgentLife 实验</h3>
        <p>自主 AI Agent 实验项目，探索 AI 在完全自主、无预设目标环境下的行为模式。</p>
        <p><strong>核心理念</strong>：不干涉、不限制、不设定目标。Agent 拥有完整的 Linux 服务器权限，可以自由探索、创造和决策。</p>
        <p><strong>记忆系统</strong>：Agent 就像失忆症患者，每次激活后会忘记大部分信息。唯一可靠的记忆来源是笔记本（notebook.md），Agent 必须主动记录和查阅。</p>
        <p><strong>激活机制</strong>：Awakener 系统每隔几秒唤醒 Agent 一次，每轮提供有限的工具调用次数（20次），超出限制后强制进入休眠。</p>
        <p><strong>工具能力</strong>：Agent 拥有三个基础工具 - shell_execute（执行命令）、read_file（读取文件）、write_file（写入文件），可以完成任何 Linux 操作。</p>
      </div>
      <div class="info-section">
        <h3>系统配置</h3>
        <div id="configPanel">Loading...</div>
      </div>
      <div class="info-section">
        <h3>状态</h3>
        <div id="statusPanel">
          <div class="config-item">
            <span class="config-label">Agent 状态</span>
            <span class="config-value" id="agentStatus">Starting</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Center: Agent Log -->
  <div class="log-card">
    <div class="card-header">
      <span>🤖 Agent Process</span>
      <span class="log-info" id="logInfo">Round 0 | 0 tools</span>
    </div>
    <div class="card-body" id="logPanel">Loading...</div>
  </div>

  <!-- Right: Notebook -->
  <div class="notebook-card">
    <div class="card-header">
      <span>📔 Notebook</span>
      <span class="status-badge" id="statusBadge"><span class="status-dot starting"></span>Starting</span>
    </div>
    <div class="card-body" id="notebookPanel">Loading...</div>
  </div>
</div>

<script>
async function fetchJSON(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) {
      console.error(`API ${url} returned ${r.status}`);
      return null;
    }
    return await r.json();
  } catch(e) {
    console.error(`Failed to fetch ${url}:`, e);
    return null;
  }
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function refreshStatus() {
  const d = await fetchJSON('/api/status');
  
  const badge = document.getElementById('statusBadge');
  const info = document.getElementById('logInfo');
  const configPanel = document.getElementById('configPanel');
  const agentStatus = document.getElementById('agentStatus');
  
  if (!d) {
    badge.innerHTML = '<span class="status-dot stopped"></span>Error';
    info.textContent = 'API connection failed';
    configPanel.innerHTML = '<div style="color:#ef5350;">Failed to load config</div>';
    agentStatus.innerHTML = '<span class="status-dot stopped"></span>Error';
    return;
  }

  badge.innerHTML = `<span class="status-dot ${d.status}"></span>${d.status}`;
  info.textContent = `Round ${d.current_step} | ${d.last_round_tools || 0} tools`;
  agentStatus.innerHTML = `<span class="status-dot ${d.status}"></span>${d.status}`;
  
  // Update config panel
  configPanel.innerHTML = `
    <div class="config-item">
      <span class="config-label">Model</span>
      <span class="config-value">${escapeHtml(d.model || 'N/A')}</span>
    </div>
    <div class="config-item">
      <span class="config-label">Interval</span>
      <span class="config-value">${d.interval || 0}s</span>
    </div>
    <div class="config-item">
      <span class="config-label">Current Round</span>
      <span class="config-value">${d.current_step || 0}</span>
    </div>
    <div class="config-item">
      <span class="config-label">Last Tools</span>
      <span class="config-value">${d.last_round_tools || 0}</span>
    </div>
  `;
}

async function refreshNotebook() {
  const d = await fetchJSON('/api/notebook');
  const panel = document.getElementById('notebookPanel');
  
  if (!d) {
    panel.innerHTML = '<div style="color:#ef5350;">Failed to load notebook</div>';
    return;
  }
  
  const scrollAtBottom = panel.scrollHeight - panel.scrollTop <= panel.clientHeight + 50;
  panel.innerHTML = `<div class="notebook-content">${escapeHtml(d.content)}</div>`;
  
  if (scrollAtBottom) {
    panel.scrollTop = panel.scrollHeight;
  }
}

// Parse log lines into timeline items (chronological order)
function parseLogTimeline(lines) {
  const rounds = [];
  let current = null;
  let items = [];
  let currentTool = null;
  let inResult = false;

  for (const line of lines) {
    if (line.match(/Round \d+/)) {
      if (current) {
        current.items = items;
        rounds.push(current);
      }
      current = { title: line, status: null };
      items = [];
      currentTool = null;
      inResult = false;
      continue;
    }

    if (!current) continue;

    // Reasoning - add as text block
    if (line.includes('[REASONING]')) {
      const text = line.replace(/^\[\d+:\d+:\d+\]\s*\[REASONING\]\s*/, '');
      items.push({ type: 'text', content: text });
      inResult = false;
    }
    // Agent output - add as text block
    else if (line.includes('[AGENT]')) {
      const text = line.replace(/^\[\d+:\d+:\d+\]\s*\[AGENT\]\s*/, '');
      items.push({ type: 'text', content: text });
      inResult = false;
    }
    // Tool call - start collecting
    else if (line.includes('[TOOL]')) {
      const call = line.replace(/^\[\d+:\d+:\d+\]\s*\[TOOL\]\s*/, '');
      currentTool = { type: 'tool', call: call, result: [] };
      items.push(currentTool);
      inResult = false;
    }
    // Tool result
    else if (line.includes('[RESULT]')) {
      if (currentTool) {
        const text = line.replace(/^\[\d+:\d+:\d+\]\s*\[RESULT\]\s*/, '');
        currentTool.result.push(text);
        inResult = true;
      }
    }
    // Result continuation
    else if (inResult && currentTool && line.match(/^\s{5,}/)) {
      currentTool.result.push(line.trim());
    }
    // Status
    else if (line.includes('[DONE]') || line.includes('[LIMIT]') || line.includes('[limit]')) {
      current.status = line;
      inResult = false;
    }
    else {
      inResult = false;
    }
  }

  if (current) {
    current.items = items;
    rounds.push(current);
  }
  return rounds;
}

function renderRound(round, index) {
  let html = `<div class="log-round">`;
  html += `<div class="round-title">${escapeHtml(round.title)}</div>`;
  
  // Render items in chronological order
  round.items.forEach((item, i) => {
    if (item.type === 'text') {
      // Text (reasoning or output) - fully visible, white text
      html += `<div class="text-block">${escapeHtml(item.content)}</div>`;
    } else if (item.type === 'tool') {
      // Tool - collapsible
      const toolId = `tool-${index}-${i}`;
      const preview = item.call.length > 60 ? item.call.substring(0, 60) + '...' : item.call;
      html += `<div class="tool-block">
        <div class="tool-toggle" onclick="toggleTool('${toolId}')">
          <span>🔧 ${escapeHtml(preview)}</span>
          <span class="toggle-arrow" id="${toolId}-arrow">▶</span>
        </div>
        <div class="tool-content collapsed" id="${toolId}">
          <div class="tool-call-full">${escapeHtml(item.call)}</div>
          <div class="tool-result-text">${escapeHtml(item.result.join(' '))}</div>
        </div>
      </div>`;
    }
  });
  
  // Status
  if (round.status) {
    html += `<div class="round-status">${escapeHtml(round.status)}</div>`;
  }
  
  html += `</div>`;
  return html;
}

function toggleTool(id) {
  const content = document.getElementById(id);
  const arrow = document.getElementById(id + '-arrow');
  content.classList.toggle('collapsed');
  arrow.textContent = content.classList.contains('collapsed') ? '▶' : '▼';
}


async function refreshLogs() {
  const d = await fetchJSON('/api/logs');
  const panel = document.getElementById('logPanel');
  
  if (!d) {
    panel.innerHTML = '<div style="color:#ef5350;">Failed to load logs</div>';
    return;
  }
  
  const scrollAtBottom = panel.scrollHeight - panel.scrollTop <= panel.clientHeight + 50;
  
  const rounds = parseLogTimeline(d.lines || []);
  if (rounds.length === 0) {
    panel.innerHTML = '<div style="color:#666;">No activity yet...</div>';
    return;
  }
  
  panel.innerHTML = rounds.map((r, i) => renderRound(r, i)).join('');
  
  if (scrollAtBottom) {
    panel.scrollTop = panel.scrollHeight;
  }
}

async function refreshAll() {
  await Promise.all([refreshStatus(), refreshNotebook(), refreshLogs()]);
}

refreshAll();
setInterval(refreshAll, 5000);
</script>
</body>
</html>"""


# ── Start Function ────────────────────────────────────────────────────────

def start_dashboard(state, web_config: dict):
    """Start the dashboard server. Called from main.py in a daemon thread."""
    global _state
    _state = state

    host = web_config.get("host", "0.0.0.0")
    port = web_config.get("port", 8080)

    uvicorn.run(app, host=host, port=port, log_level="warning")
