/**
 * Awakener - Memory Page Logic
 * ===============================
 * Displays the agent's notebook entries (one per activation round).
 * Entries are shown newest-first, with full content visible.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- DOM references -------------------------------------------------------
  const memoryBody = document.getElementById('memory-body');
  const memoryMeta = document.getElementById('memory-meta');

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
        var card = document.createElement('div');
        card.className = 'memory-card';

        var time = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '';
        var round = entry.round || '?';
        var content = entry.content || '';

        card.innerHTML =
          '<div class="memory-card-header">' +
            '<span class="badge badge-primary">Round ' + round + '</span>' +
            '<span class="text-xs text-muted">' + escapeHtml(time) + '</span>' +
          '</div>' +
          '<div class="memory-card-content">' + formatContent(content) + '</div>';

        memoryBody.appendChild(card);
      });
    } catch (e) {
      memoryBody.innerHTML =
        '<span class="text-danger">Failed to load notebook: ' + escapeHtml(e.message) + '</span>';
    }
  };

  // ========================================================================
  // Utility
  // ========================================================================

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
