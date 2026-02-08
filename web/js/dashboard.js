/**
 * Awakener - Dashboard Page Logic
 * ==================================
 * Handles:
 *   - WebSocket connection for real-time log streaming and status updates
 *   - Agent control actions (start / stop / restart)
 *   - Inspiration message sending
 *   - Stats display (round, status, tool calls, uptime)
 *   - Auto-scrolling log panel
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- DOM references -------------------------------------------------------
  const logBody      = document.getElementById('log-body');
  const autoScroll   = document.getElementById('auto-scroll');
  const statRound    = document.getElementById('stat-round');
  const statStatus   = document.getElementById('stat-status');
  const statTools    = document.getElementById('stat-tools');
  const statUptime   = document.getElementById('stat-uptime');
  const btnStart     = document.getElementById('btn-start');
  const btnStop      = document.getElementById('btn-stop');
  const btnRestart   = document.getElementById('btn-restart');
  const statusBadge  = document.getElementById('agent-status');
  const statusText   = document.getElementById('agent-status-text');
  const statusDot    = statusBadge ? statusBadge.querySelector('.status-dot') : null;

  // -- State ----------------------------------------------------------------
  let ws = null;
  let totalToolCalls = 0;
  let startTime = null;
  let uptimeTimer = null;

  // -- WebSocket connection -------------------------------------------------

  /**
   * Establish a WebSocket connection for real-time updates.
   * Automatically reconnects on disconnect with exponential backoff.
   */
  function connectWS() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = protocol + '//' + location.host + '/ws';

    ws = new WebSocket(url);

    ws.onopen = function() {
      appendLog('Connected to agent stream', 'system');
    };

    ws.onmessage = function(event) {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        appendLog(event.data, 'system');
      }
    };

    ws.onclose = function() {
      appendLog('Disconnected. Reconnecting in 3s...', 'system');
      setTimeout(connectWS, 3000);
    };

    ws.onerror = function() {
      // onclose will fire after this
    };
  }

  /**
   * Handle a parsed WebSocket message from the server.
   *
   * Message types from activator (loop.py):
   *   - "status"      : { status, next_in?, message? }
   *   - "log"         : { text }
   *   - "round"       : { step, event, tools_used?, duration?, notebook_saved? }
   *   - "tool_call"   : { name, args }
   *   - "tool_result" : { text }
   *   - "thought"     : { text }
   *
   * @param {Object} msg - The parsed message object.
   */
  function handleMessage(msg) {
    var d = msg.data || {};

    switch (msg.type) {
      case 'status':
        updateStatus(d);
        break;

      case 'round':
        if (d.event === 'started') {
          appendLog('═══ Round ' + d.step + ' ═══', 'round');
          statRound.textContent = d.step || '-';
        } else if (d.event === 'completed') {
          appendLog(
            '[DONE] Round ' + d.step + ' | Tools: ' + (d.tools_used || 0) +
            ' | Time: ' + (d.duration || '?') + 's | Note: ' +
            (d.notebook_saved ? 'saved' : 'NOT SAVED'),
            'system'
          );
        }
        break;

      case 'tool_call':
        var argsStr = '';
        try { argsStr = JSON.stringify(d.args || {}); } catch(e) { argsStr = '{}'; }
        if (argsStr.length > 200) argsStr = argsStr.substring(0, 200) + '...';
        appendLog('[TOOL] ' + d.name + '(' + argsStr + ')', 'tool');
        totalToolCalls++;
        statTools.textContent = totalToolCalls;
        break;

      case 'tool_result':
        var preview = (d.text || '').substring(0, 300);
        appendLog('[RESULT] ' + preview, 'result');
        break;

      case 'thought':
        var thought = (d.text || '').substring(0, 500);
        appendLog('[THOUGHT] ' + thought, 'thought');
        break;

      case 'log':
        appendLog(d.text || d.message || '', 'system');
        break;

      case 'error':
        appendLog('[ERROR] ' + (d.message || d.text || ''), 'error');
        break;

      default:
        // Show raw message for unknown types
        appendLog(JSON.stringify(msg), 'system');
    }
  }

  /**
   * Update the agent status display (badge + stats).
   * @param {Object} data - Status data from WS or REST API.
   *   WS format: { status, next_in?, message? }
   *   REST format: { state, is_running, current_round, ... }
   */
  function updateStatus(data) {
    // Support both WS format (status) and REST format (state)
    const status = data.status || data.state || 'idle';

    // Update badge
    if (statusBadge) statusBadge.className = 'agent-status ' + status;
    if (statusText) statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    statStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    // Show waiting info
    if (status === 'waiting' && data.next_in) {
      statStatus.textContent = 'Waiting (' + data.next_in + 's)';
    }

    // Pulse animation for running
    if (statusDot) {
      statusDot.classList.toggle('pulse', status === 'running');
    }

    // Update round (WS sends 'round', REST sends 'current_round' or 'current_step')
    var round = data.round || data.current_round || data.current_step;
    if (round !== undefined) {
      statRound.textContent = round;
    }

    // Button states
    const isRunning = (status === 'running');
    btnStart.disabled = isRunning;
    btnStop.disabled = !isRunning;
    btnRestart.disabled = !isRunning;

    // Uptime tracking
    if (isRunning && !startTime) {
      startTime = Date.now();
      uptimeTimer = setInterval(updateUptime, 1000);
    } else if (!isRunning) {
      startTime = null;
      if (uptimeTimer) clearInterval(uptimeTimer);
      statUptime.textContent = '-';
    }
  }

  /**
   * Update the uptime display (HH:MM:SS).
   */
  function updateUptime() {
    if (!startTime) return;
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const h = Math.floor(elapsed / 3600);
    const m = Math.floor((elapsed % 3600) / 60);
    const s = elapsed % 60;
    statUptime.textContent =
      String(h).padStart(2, '0') + ':' +
      String(m).padStart(2, '0') + ':' +
      String(s).padStart(2, '0');
  }

  // -- Log panel ------------------------------------------------------------

  /**
   * Append a line to the log panel.
   * @param {string} text  - The log text.
   * @param {string} level - CSS class suffix: system, tool, result, thought, error, round.
   */
  function appendLog(text, level) {
    const line = document.createElement('div');
    line.className = 'log-line log-' + (level || 'system');

    // Add timestamp prefix
    const now = new Date();
    const ts = String(now.getHours()).padStart(2, '0') + ':' +
               String(now.getMinutes()).padStart(2, '0') + ':' +
               String(now.getSeconds()).padStart(2, '0');
    line.textContent = '[' + ts + '] ' + text;

    logBody.appendChild(line);

    // Limit displayed lines (keep last 500)
    while (logBody.childNodes.length > 500) {
      logBody.removeChild(logBody.firstChild);
    }

    // Auto-scroll
    if (autoScroll.checked) {
      logBody.scrollTop = logBody.scrollHeight;
    }
  }

  // -- Agent actions --------------------------------------------------------

  /**
   * Send a control command to the agent (start / stop / restart).
   * @param {string} action - One of: start, stop, restart.
   */
  window.agentAction = async function(action) {
    try {
      await api.post('/api/agent/' + action);
      toast('Agent ' + action + ' command sent', 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  /**
   * Send an inspiration message to the agent.
   * The agent sees this as a "spark of inspiration" at the start of the next round.
   */
  window.sendInspiration = async function() {
    const input = document.getElementById('inspiration-input');
    const message = input.value.trim();
    if (!message) return;

    try {
      await api.post('/api/agent/inspiration', { message: message });
      toast('Inspiration sent to agent', 'success');
      input.value = '';
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  /**
   * Clear the log panel.
   */
  window.clearLogs = function() {
    logBody.innerHTML = '<div class="log-line log-system">Log cleared.</div>';
    totalToolCalls = 0;
    statTools.textContent = '0';
  };

  // -- Handle Enter key in inspiration input ----------------------------------
  document.getElementById('inspiration-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      window.sendInspiration();
    }
  });

  // -- Init -----------------------------------------------------------------

  /**
   * Fetch initial agent status from REST API, then connect WebSocket.
   */
  async function init() {
    try {
      const status = await api.get('/api/agent/status');
      updateStatus(status);
    } catch (e) {
      // API might not be ready yet
    }

    connectWS();

    // Apply i18n
    if (typeof i18n !== 'undefined') i18n.apply();
  }

  init();
})();
