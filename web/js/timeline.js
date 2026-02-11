/**
 * Awakener - Timeline Page Logic
 * =================================
 * Handles:
 *   - Lazy-loading timeline entries (initial 5, load 5 more each time)
 *   - Rendering per-round summaries with collapsible content
 *   - Collapsed: First thought + last 20 lines of output
 *   - Expanded: Full summary
 *
 * Timeline entries contain: round, timestamp, tools_used, duration, summary, action_log.
 * Each entry represents one completed activation round.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- State ----------------------------------------------------------------
  let allEvents     = [];      // All loaded events so far
  let totalEvents   = 0;       // Total events in DB
  let loadedCount   = 0;       // How many events we've fetched
  const LOAD_SIZE   = 5;       // Load 5 at a time

  // -- DOM references -------------------------------------------------------
  const timelineEl    = document.getElementById('timeline');
  const loadMoreBtn   = document.getElementById('load-more-btn');
  const loadMoreWrap  = document.getElementById('load-more-wrap');

  // ========================================================================
  // Load timeline data (lazy loading)
  // ========================================================================

  /**
   * Initial load: fetch first 5 events.
   */
  window.loadTimeline = async function() {
    allEvents = [];
    loadedCount = 0;
    timelineEl.innerHTML = '';
    await loadMore();
  };

  /**
   * Load next batch of events (5 more).
   */
  async function loadMore() {
    try {
      var params = new URLSearchParams({
        offset: loadedCount,
        limit: LOAD_SIZE,
      });

      const data = await api.get('/api/timeline?' + params.toString());
      totalEvents = data.total || 0;
      const newEvents = data.events || [];

      allEvents = allEvents.concat(newEvents);
      loadedCount += newEvents.length;

      renderNewEvents(newEvents);
      updateLoadMoreButton();
    } catch (e) {
      timelineEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">&#x26A0;</div>' +
        '<p>Failed to load timeline: ' + escapeHtml(e.message) + '</p>' +
        '</div>';
    }
  }

  /**
   * Render newly loaded events (append to timeline).
   * @param {Array} events - Array of timeline entry objects.
   */
  function renderNewEvents(events) {
    if (allEvents.length === 0 && events.length === 0) {
      timelineEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">&#x1F4C5;</div>' +
        '<p>No activation rounds recorded yet.</p>' +
        '</div>';
      return;
    }

    events.forEach(function(event) {
      var item = document.createElement('div');
      item.className = 'timeline-item';

      var dotClass = 'timeline-dot round';
      var time = formatTime(event.timestamp);
      var round = event.round || '?';
      var tools = event.tools_used || 0;
      var duration = event.duration ? event.duration.toFixed(1) + 's' : '?';
      var summary = event.summary || '';
      var actionLog = event.action_log || '';

      var statsHtml =
        '<span class="badge badge-primary">Round ' + round + '</span> ' +
        '<span class="badge badge-info">Tools: ' + tools + '</span> ' +
        '<span class="text-xs text-muted">' + duration + '</span>';

      // Build collapsed and full content
      var collapsedHtml = buildCollapsedSummary(actionLog, summary);
      var fullHtml = buildFullSummary(summary);

      var itemId = 'tl-' + round;

      item.innerHTML =
        '<div class="' + dotClass + '"></div>' +
        '<div class="timeline-content">' +
          '<div class="timeline-time flex flex-between flex-center">' +
            '<div>' + statsHtml + ' &mdash; ' + escapeHtml(time) + '</div>' +
            '<button class="btn btn-sm btn-danger" onclick="deleteTimelineEntry(' + round + ')" title="Delete">' +
              '&#x1F5D1;' +
            '</button>' +
          '</div>' +
          '<div class="timeline-body">' +
            '<div id="' + itemId + '-collapsed" class="timeline-summary-collapsed">' + collapsedHtml + '</div>' +
            '<div id="' + itemId + '-full" class="timeline-summary-full" style="display:none">' + fullHtml + '</div>' +
            '<a href="javascript:void(0)" class="timeline-toggle" onclick="toggleSummary(\'' + itemId + '\')">' +
              '<span data-i18n="timeline.showMore">Expand</span>' +
            '</a>' +
          '</div>' +
        '</div>';

      timelineEl.appendChild(item);
    });
  }

  /**
   * Build collapsed summary: first thought + first 20 lines of formal output.
   * The summary field mixes [Thinking] lines and formal content together.
   * We split them: first [Thinking] line as the thought, then find the
   * formal content (lines without [Thinking] tag) and show its first 20 lines.
   * @param {string} actionLog - Brief action log (unused, kept for API compat).
   * @param {string} summary - Full summary text (thinking + formal output).
   * @returns {string} HTML for collapsed view.
   */
  function buildCollapsedSummary(actionLog, summary) {
    if (!summary) return '<p class="text-muted">(no content)</p>';

    var html = '';
    var lines = summary.split('\n');

    // 1. Extract first [Thinking] line
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].includes('[Thinking]')) {
        var match = lines[i].match(/\[Thinking\]\s*(.*)/);
        if (match && match[1]) {
          html += '<div class="timeline-thought">' +
                  '<strong>[Thinking]</strong> ' +
                  escapeHtml(match[1].trim()) +
                  '</div>';
          break;
        }
      }
    }

    // 2. Extract formal output: lines that do NOT start with [Thinking]
    var formalLines = [];
    for (var j = 0; j < lines.length; j++) {
      var trimmed = lines[j].trim();
      // Skip lines containing [Thinking] tag (with or without timestamp prefix)
      if (trimmed === '' && formalLines.length === 0) continue; // skip leading blanks
      if (/\[Thinking\]/.test(lines[j])) continue;
      formalLines.push(lines[j]);
    }

    if (formalLines.length > 0) {
      var preview = formalLines.slice(0, 20).join('\n');
      html += '<pre class="timeline-output">' + escapeHtml(preview) + '</pre>';
    }

    return html || '<p class="text-muted">(no content)</p>';
  }

  /**
   * Build full summary: entire summary text.
   * @param {string} summary - Full summary text.
   * @returns {string} HTML for expanded view.
   */
  function buildFullSummary(summary) {
    if (!summary) return '<p class="text-muted">(no summary)</p>';
    return '<pre class="timeline-summary">' + escapeHtml(summary) + '</pre>';
  }

  /**
   * Extract the first thought block from action_log.
   * Action log format: "[HH:MM:SS] [THOUGHT] text"
   * May span multiple lines if the thought is long.
   * @param {string} actionLog - Action log text.
   * @returns {string} First thought content or empty string.
   */
  function extractFirstThought(actionLog) {
    if (!actionLog) return '';
    var lines = actionLog.split('\n');
    var thoughtLines = [];
    var inThought = false;

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      
      // Check if this line starts a THOUGHT block
      if (line.includes('[THOUGHT]')) {
        inThought = true;
        // Extract text after [THOUGHT]
        var match = line.match(/\[THOUGHT\]\s*(.*)/);
        if (match && match[1]) {
          thoughtLines.push(match[1].trim());
        }
      } else if (inThought) {
        // Continue reading until we hit another tag or empty line
        if (line.match(/\[(TOOL|RESULT|LOADING)\]/) || line.trim() === '') {
          break;
        }
        thoughtLines.push(line.trim());
      }
    }

    return thoughtLines.join(' ');
  }

  /**
   * Extract the first N lines from text.
   * @param {string} text - Text to extract from.
   * @param {number} n - Number of lines to extract.
   * @returns {string} First N lines joined with newlines.
   */
  function extractFirstLines(text, n) {
    if (!text) return '';
    var lines = text.split('\n');
    return lines.slice(0, n).join('\n');
  }

  /**
   * Toggle between collapsed and expanded view.
   * @param {string} id - The item ID prefix (e.g. 'tl-42').
   */
  window.toggleSummary = function(id) {
    var collapsed = document.getElementById(id + '-collapsed');
    var full = document.getElementById(id + '-full');
    var link = collapsed ? collapsed.parentElement.querySelector('.timeline-toggle') : null;
    if (!collapsed || !full) return;

    if (full.style.display === 'none') {
      // Expand
      collapsed.style.display = 'none';
      full.style.display = '';
      if (link) link.innerHTML = '<span data-i18n="timeline.showLess">Collapse</span>';
    } else {
      // Collapse
      collapsed.style.display = '';
      full.style.display = 'none';
      if (link) link.innerHTML = '<span data-i18n="timeline.showMore">Expand</span>';
    }
  };

  /**
   * Update "Load More" button visibility and state.
   */
  function updateLoadMoreButton() {
    if (!loadMoreWrap || !loadMoreBtn) return;

    if (loadedCount >= totalEvents) {
      // All loaded
      loadMoreWrap.style.display = 'none';
    } else {
      loadMoreWrap.style.display = '';
      var remaining = totalEvents - loadedCount;
      loadMoreBtn.textContent = 'Load More (' + remaining + ' remaining)';
    }
  }

  /**
   * Attach load more button click handler.
   */
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function() {
      loadMore();
    });
  }

  // ========================================================================
  // Filter (simplified -- no type filtering needed for round-based timeline)
  // ========================================================================

  /**
   * Set filter is kept for backward-compatible HTML buttons.
   * Now it's a no-op since all entries are rounds.
   */
  window.setFilter = function(filter) {
    // All entries are round summaries, so filtering is not needed.
    // Just reload.
    loadTimeline();
  };

  // ========================================================================
  // Delete
  // ========================================================================

  /**
   * Delete a timeline entry by round number.
   * @param {number} round - The round number to delete.
   */
  window.deleteTimelineEntry = async function(round) {
    if (!confirm('Delete Round ' + round + '?\nThis will also remove the log for this round.')) return;

    try {
      await api.delete('/api/timeline/' + round);
      toast('Round ' + round + ' deleted', 'success');
      loadTimeline();
    } catch (e) {
      toast('Failed to delete: ' + e.message, 'error');
    }
  };

  // ========================================================================
  // Utility
  // ========================================================================

  /**
   * Format a timestamp string for display.
   * @param {string} ts - ISO 8601 timestamp or Unix epoch.
   * @returns {string} Formatted time string.
   */
  function formatTime(ts) {
    if (!ts) return '';
    try {
      var d = new Date(ts);
      return d.toLocaleString();
    } catch (e) {
      return String(ts);
    }
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  loadTimeline();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
