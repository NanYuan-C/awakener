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
  const btnStart       = document.getElementById('btn-start');
  const btnStop        = document.getElementById('btn-stop');
  const toolbarStatus  = document.getElementById('toolbar-status');     // dashboard toolbar badge

  // -- State ----------------------------------------------------------------
  let ws = null;
  let roundStartTime = null;   // ISO timestamp of current round start (from backend)
  let roundToolsUsed = 0;      // Tools used in current round (from backend)
  let uptimeTimer = null;
  let liveThoughtEl = null;    // Currently streaming thought element
  let liveThoughtText = '';    // Accumulated streaming thought content
  let loadingEl = null;        // Current loading indicator element
  let loadingTimer = null;     // Interval for animating dots
  let loadingDots = 0;         // Current dot count (0-3)

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
      // Fetch current status on every (re)connect to stay in sync
      fetchStatus();
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
   *   - "status"       : { status, next_in?, message? }
   *   - "log"          : { text }
   *   - "loading"      : { text }           (animated dots, auto-removed on next msg)
   *   - "round"        : { step, event, tools_used?, duration? }
   *   - "tool_call"    : { name, args }
   *   - "tool_result"  : { text }
   *   - "thought"      : { text }           (non-streaming fallback)
   *   - "thought_chunk": { text }           (streaming: partial thought delta)
   *   - "thought_done" : { text }           (streaming: final complete thought)
   *
   * @param {Object} msg - The parsed message object.
   */
  function handleMessage(msg) {
    var d = msg.data || {};

    // Any non-loading message removes the current loading indicator
    if (msg.type !== 'loading' && msg.type !== 'loading_update') {
      removeLoading();
    }

    switch (msg.type) {
      case 'loading':
        showLoading(d.text || 'Loading');
        break;

      case 'loading_update':
        // Update existing loading indicator text (real-time progress)
        if (loadingEl) {
          var now = new Date();
          var ts = String(now.getHours()).padStart(2, '0') + ':' +
                   String(now.getMinutes()).padStart(2, '0') + ':' +
                   String(now.getSeconds()).padStart(2, '0');
          loadingEl.dataset.prefix = '[' + ts + '] ' + (d.text || '');
          loadingEl.textContent = loadingEl.dataset.prefix + '.'.repeat(loadingDots);
        }
        break;

      case 'status':
        updateStatus(d);
        break;

      case 'round':
        // Round start event with round_start_time and round_tools_used
        if (msg.round !== undefined && msg.round_start_time !== undefined) {
          roundStartTime = msg.round_start_time;
          roundToolsUsed = msg.round_tools_used || 0;
          statRound.textContent = msg.round;
          statTools.textContent = roundToolsUsed;
          // Start uptime timer
          if (!uptimeTimer) {
            uptimeTimer = setInterval(updateUptime, 1000);
          }
          updateUptime();
        }
        // Legacy event handling (from old message format)
        if (d.event === 'started') {
          appendLog('═══ Round ' + d.step + ' ═══', 'round');
        } else if (d.event === 'completed') {
          appendLog(
            '[DONE] Round ' + d.step + ' | Tools: ' + (d.tools_used || 0) +
            ' | Time: ' + (d.duration || '?') + 's',
            'system'
          );
        }
        break;

      case 'tools':
        // Real-time tool count update from backend
        if (msg.round_tools_used !== undefined) {
          roundToolsUsed = msg.round_tools_used;
          statTools.textContent = roundToolsUsed;
        }
        break;

      case 'tool_call':
        var argsStr = '';
        try { argsStr = JSON.stringify(d.args || {}); } catch(e) { argsStr = '{}'; }
        if (argsStr.length > 200) argsStr = argsStr.substring(0, 200) + '...';
        appendLog('[TOOL] ' + d.name + '(' + argsStr + ')', 'tool');
        // Note: tool count now updated via 'tools' message from backend
        break;

      case 'tool_result':
        var preview = (d.text || '').substring(0, 300);
        appendLog('[RESULT] ' + preview, 'result');
        break;

      case 'thought':
        // Non-streaming fallback (used if streaming is not active)
        finalizeLiveThought();
        appendLog('[THOUGHT] ' + (d.text || ''), 'thought');
        break;

      case 'thought_chunk':
        // Streaming thought: create or update the live thought element
        if (!liveThoughtEl) {
          liveThoughtEl = document.createElement('div');
          liveThoughtEl.className = 'log-line log-thought live-thought';
          liveThoughtText = '';
          // Timestamp for when the thought started
          var now = new Date();
          var ts = String(now.getHours()).padStart(2, '0') + ':' +
                   String(now.getMinutes()).padStart(2, '0') + ':' +
                   String(now.getSeconds()).padStart(2, '0');
          liveThoughtEl.dataset.prefix = '[' + ts + '] [THOUGHT] ';
          liveThoughtEl.textContent = liveThoughtEl.dataset.prefix + '▊';
          logBody.appendChild(liveThoughtEl);
        }
        liveThoughtText += (d.text || '');
        liveThoughtEl.textContent = liveThoughtEl.dataset.prefix + liveThoughtText + '▊';
        // Auto-scroll
        if (autoScroll.checked) {
          logBody.scrollTop = logBody.scrollHeight;
        }
        break;

      case 'thought_done':
        // Finalize the streaming thought element
        if (liveThoughtEl) {
          liveThoughtEl.textContent = liveThoughtEl.dataset.prefix + (d.text || liveThoughtText || '');
          liveThoughtEl.classList.remove('live-thought');
          liveThoughtEl = null;
          liveThoughtText = '';
          // Auto-scroll
          if (autoScroll.checked) {
            logBody.scrollTop = logBody.scrollHeight;
          }
        } else {
          // No live element, just append as regular thought
          appendLog('[THOUGHT] ' + (d.text || ''), 'thought');
        }
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

    // Update toolbar badge
    if (toolbarStatus) {
      toolbarStatus.className = 'agent-status ' + status;
      var tbDot = toolbarStatus.querySelector('.status-dot');
      if (tbDot) tbDot.classList.toggle('pulse', status === 'running');
    }
    statStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    // Show waiting info
    if (status === 'waiting' && data.next_in) {
      statStatus.textContent = 'Waiting (' + data.next_in + 's)';
    }

    // Update round (WS sends 'round', REST sends 'current_round' or 'current_step')
    var round = data.round || data.current_round || data.current_step;
    if (round !== undefined) {
      statRound.textContent = round;
    }

    // Update round timing and tool count (from status API on page load/refresh)
    if (data.round_start_time) {
      roundStartTime = data.round_start_time;
      if (!uptimeTimer && (status === 'running' || status === 'waiting')) {
        uptimeTimer = setInterval(updateUptime, 1000);
      }
      updateUptime();
    }
    if (data.round_tools_used !== undefined) {
      roundToolsUsed = data.round_tools_used;
      statTools.textContent = roundToolsUsed;
    }

    // Button states based on current status
    const isRunning = (status === 'running' || status === 'waiting');
    const isStopping = (status === 'stopping');
    
    // Start button: disabled when running, waiting, or stopping
    btnStart.disabled = isRunning || isStopping;
    // Stop button: disabled when idle, error, or already stopping
    btnStop.disabled = !isRunning;

    // Uptime timer: stop when idle/error/stopped
    if (status === 'idle' || status === 'error') {
      roundStartTime = null;
      roundToolsUsed = 0;
      if (uptimeTimer) {
        clearInterval(uptimeTimer);
        uptimeTimer = null;
      }
      statUptime.textContent = '-';
      statTools.textContent = '0';
    }
  }

  /**
   * Update the uptime display (HH:MM:SS) based on roundStartTime.
   */
  function updateUptime() {
    if (!roundStartTime) {
      statUptime.textContent = '-';
      return;
    }
    const start = new Date(roundStartTime).getTime();
    const elapsed = Math.floor((Date.now() - start) / 1000);
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
   * Show an animated loading indicator in the log panel.
   * The text is displayed with cycling dots: (empty) → . → .. → ...
   * Replaces any existing loading indicator.
   *
   * @param {string} text - The loading text (without trailing dots).
   */
  function showLoading(text) {
    removeLoading();

    loadingEl = document.createElement('div');
    loadingEl.className = 'log-line log-loading';

    var now = new Date();
    var ts = String(now.getHours()).padStart(2, '0') + ':' +
             String(now.getMinutes()).padStart(2, '0') + ':' +
             String(now.getSeconds()).padStart(2, '0');
    loadingEl.dataset.prefix = '[' + ts + '] ' + text;
    loadingDots = 0;
    loadingEl.textContent = loadingEl.dataset.prefix;

    logBody.appendChild(loadingEl);

    // Animate dots: (empty) → . → .. → ... → (empty) → ...
    loadingTimer = setInterval(function() {
      loadingDots = (loadingDots + 1) % 4;
      loadingEl.textContent = loadingEl.dataset.prefix + '.'.repeat(loadingDots);
    }, 400);

    if (autoScroll.checked) {
      logBody.scrollTop = logBody.scrollHeight;
    }
  }

  /**
   * Remove the current loading indicator and stop its animation.
   * Called automatically when any non-loading message arrives.
   */
  function removeLoading() {
    if (loadingTimer) {
      clearInterval(loadingTimer);
      loadingTimer = null;
    }
    if (loadingEl) {
      loadingEl.remove();
      loadingEl = null;
    }
    loadingDots = 0;
  }

  /**
   * Finalize any currently-streaming thought element.
   * Called when a new message type arrives that means the thought is done.
   */
  function finalizeLiveThought() {
    if (liveThoughtEl) {
      liveThoughtEl.textContent = liveThoughtEl.dataset.prefix + liveThoughtText;
      liveThoughtEl.classList.remove('live-thought');
      liveThoughtEl = null;
      liveThoughtText = '';
    }
  }

  /**
   * Append a line to the log panel.
   * @param {string} text  - The log text.
   * @param {string} level - CSS class suffix: system, tool, result, thought, error, round.
   */
  function appendLog(text, level) {
    // If there's a live thought and we're adding a non-chunk message, finalize it
    if (liveThoughtEl && level !== 'thought') {
      finalizeLiveThought();
    }
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
    // Instant UI feedback for stop/restart — don't wait for server
    if (action === 'stop' || action === 'restart') {
      // Immediately disable buttons and show stopping state
      btnStart.disabled = true;
      btnStop.disabled = true;
      updateStatus({status: 'stopping'});
      toast('Stopping agent, finishing current round...', 'info');
    }

    try {
      const result = await api.post('/api/agent/' + action);
      if (action === 'start') {
        toast('Agent started', 'success');
      } else if (action === 'stop') {
        toast('Stop command received, agent will stop after current round completes', 'success');
      } else if (action === 'restart') {
        toast('Agent restarted', 'success');
      }
      // Update UI with the returned status
      updateStatus(result);
    } catch (err) {
      toast(err.message, 'error');
      // Re-fetch actual status on error to correct the UI
      fetchStatus();
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

    // Instant UI feedback — clear input and disable button immediately
    input.value = '';
    if (btnSendInspiration) btnSendInspiration.disabled = true;
    toast('Sending inspiration...', 'info');

    try {
      await api.post('/api/agent/inspiration', { message: message });
      toast('Inspiration sent to agent', 'success');
    } catch (err) {
      toast(err.message, 'error');
      // Restore input on error
      input.value = message;
      if (btnSendInspiration) btnSendInspiration.disabled = false;
    }
  };

  // -- Inspiration input handling -----------------------------------------------
  var inspirationInput = document.getElementById('inspiration-input');
  var btnSendInspiration = document.getElementById('btn-send-inspiration');

  // Enable/disable send button based on input content
  inspirationInput.addEventListener('input', function() {
    btnSendInspiration.disabled = !this.value.trim();
  });

  // Send on Enter key
  inspirationInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      window.sendInspiration();
    }
  });

  // -- Init -----------------------------------------------------------------

  /**
   * Fetch the current agent status from the REST API and update the UI.
   * Called on init and on every WebSocket (re)connect to stay in sync.
   */
  async function fetchStatus() {
    try {
      const status = await api.get('/api/agent/status');
      updateStatus(status);
    } catch (e) {
      // API might not be ready yet – ignore silently
    }
  }

  /**
   * Initialise the dashboard: load current status, then open WebSocket.
   */
  async function init() {
    await fetchStatus();
    connectWS();

    // Apply i18n
    if (typeof i18n !== 'undefined') i18n.apply();
  }

  init();
})();
