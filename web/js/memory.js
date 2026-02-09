/**
 * Awakener - Memory Page Logic
 * ===============================
 * Displays the agent's notebook entries (one per activation round).
 * Entries are shown newest-first. Each card shows 10 lines by default
 * with a toggle to expand/collapse the full content.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- Config ---------------------------------------------------------------
  var MAX_LINES = 10;

  // -- DOM references -------------------------------------------------------
  var memoryBody = document.getElementById('memory-body');
  var memoryMeta = document.getElementById('memory-meta');

  // ========================================================================
  // Load notebook entries
  // ========================================================================

  /**
   * Fetch and display all notebook entries (newest first).
   */
  window.loadMemory = async function() {
    memoryBody.innerHTML = '<span class="text-muted">Loading...</span>';

    try {
      var data = await api.get('/api/memory/notebook?offset=0&limit=200');
      var entries = data.entries || [];
      var total = data.total || 0;

      memoryMeta.textContent = 'Total notes: ' + total;

      if (entries.length === 0) {
        memoryBody.innerHTML =
          '<div class="empty-state">' +
          '<div class="empty-state-icon">&#x1F4D3;</div>' +
          '<p>No notebook entries yet. The agent will write notes during each activation round.</p>' +
          '</div>';
        return;
      }

      memoryBody.innerHTML = '';

      entries.forEach(function(entry) {
        memoryBody.appendChild(createMemoryCard(entry));
      });
    } catch (e) {
      memoryBody.innerHTML =
        '<span class="text-danger">Failed to load notebook: ' + escapeHtml(e.message) + '</span>';
    }
  };

  // ========================================================================
  // Card builder (with 10-line collapse)
  // ========================================================================

  /**
   * Create a single memory card element.
   * If content exceeds MAX_LINES, only the first MAX_LINES are shown
   * with a "Show more" toggle.
   *
   * @param {Object} entry - Notebook entry {round, timestamp, content}.
   * @returns {HTMLElement} The card element.
   */
  function createMemoryCard(entry) {
    var card = document.createElement('div');
    card.className = 'memory-card';

    var time = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '';
    var round = entry.round || '?';
    var content = entry.content || '';

    var lines = content.split('\n');
    var isLong = lines.length > MAX_LINES;
    var fullHtml = formatContent(content);
    var shortHtml = isLong
      ? formatContent(lines.slice(0, MAX_LINES).join('\n'))
      : fullHtml;

    // -- Header
    var header = document.createElement('div');
    header.className = 'memory-card-header';
    header.innerHTML =
      '<span class="badge badge-primary">Round ' + round + '</span>' +
      '<span class="text-xs text-muted">' + escapeHtml(time) + '</span>';
    card.appendChild(header);

    // -- Content
    var contentDiv = document.createElement('div');
    contentDiv.className = 'memory-card-content';
    contentDiv.innerHTML = shortHtml;
    card.appendChild(contentDiv);

    // -- Toggle (only for long entries)
    if (isLong) {
      var footer = document.createElement('div');
      footer.className = 'memory-card-toggle';

      var toggle = document.createElement('a');
      toggle.className = 'memory-toggle';
      toggle.textContent = t('showMore');

      var expanded = false;
      toggle.onclick = function() {
        expanded = !expanded;
        contentDiv.innerHTML = expanded ? fullHtml : shortHtml;
        toggle.textContent = expanded ? t('showLess') : t('showMore');
      };

      footer.appendChild(toggle);
      card.appendChild(footer);
    }

    return card;
  }

  // ========================================================================
  // Utility
  // ========================================================================

  /**
   * i18n helper with fallback.
   */
  function t(key) {
    if (typeof i18n !== 'undefined' && i18n.t) return i18n.t(key);
    var fallback = { showMore: 'Show more', showLess: 'Collapse' };
    return fallback[key] || key;
  }

  /**
   * Format notebook content: escape HTML, preserve whitespace and newlines.
   * Also converts markdown-like headers (## ) to bold text.
   * @param {string} content - Raw notebook content.
   * @returns {string} Formatted HTML string.
   */
  function formatContent(content) {
    var escaped = escapeHtml(content);
    // Convert markdown headers to bold
    escaped = escaped.replace(/^### (.+)$/gm, '<strong>$1</strong>');
    escaped = escaped.replace(/^## (.+)$/gm, '<strong style="font-size:1.05em;">$1</strong>');
    escaped = escaped.replace(/^# (.+)$/gm, '<strong style="font-size:1.1em;">$1</strong>');
    // Convert **bold** to <strong>
    escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Convert markdown list items
    escaped = escaped.replace(/^- (.+)$/gm, '&bull; $1');
    // Preserve newlines
    escaped = escaped.replace(/\n/g, '<br>');
    return escaped;
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  loadMemory();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
