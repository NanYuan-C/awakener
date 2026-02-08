/**
 * Awakener - Memory Page Logic
 * ===============================
 * Handles:
 *   - Loading the agent's notebook entries from /api/memory/notebook
 *   - Displaying per-round notes as cards (newest first)
 *   - Loading recent round summaries from /api/memory/recent
 *   - Pagination support
 *
 * The notebook is now stored as notebook.jsonl with one entry per round.
 * Each entry has: round, timestamp, content.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- DOM references -------------------------------------------------------
  const memoryBody   = document.getElementById('memory-body');
  const memoryMeta   = document.getElementById('memory-meta');
  const recentEl     = document.getElementById('recent-memories');

  // Pagination state
  var currentOffset = 0;
  var pageSize = 50;

  // ========================================================================
  // Load agent notebook entries
  // ========================================================================

  /**
   * Fetch and display the agent's notebook entries (per-round notes).
   * Entries are displayed as cards in reverse chronological order.
   */
  window.loadMemory = async function() {
    memoryBody.innerHTML = '<span class="text-muted">Loading...</span>';

    try {
      var url = '/api/memory/notebook?offset=' + currentOffset + '&limit=' + pageSize;
      var data = await api.get(url);
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
        card.className = 'card mb-sm';
        card.style.padding = 'var(--spacing-md)';

        var time = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '';
        var round = entry.round || '?';
        var content = entry.content || '';

        card.innerHTML =
          '<div class="flex flex-between flex-center mb-sm">' +
            '<span class="badge badge-primary">Round ' + round + '</span>' +
            '<span class="text-xs text-muted">' + escapeHtml(time) + '</span>' +
          '</div>' +
          '<pre class="notebook-content">' + escapeHtml(content) + '</pre>';

        memoryBody.appendChild(card);
      });

      // Pagination buttons
      if (total > pageSize) {
        var nav = document.createElement('div');
        nav.className = 'flex flex-between mt-md';
        nav.innerHTML = '';

        if (currentOffset > 0) {
          var prevBtn = document.createElement('button');
          prevBtn.className = 'btn btn-outline';
          prevBtn.textContent = 'Previous';
          prevBtn.onclick = function() {
            currentOffset = Math.max(0, currentOffset - pageSize);
            loadMemory();
          };
          nav.appendChild(prevBtn);
        }

        if (currentOffset + pageSize < total) {
          var nextBtn = document.createElement('button');
          nextBtn.className = 'btn btn-outline';
          nextBtn.textContent = 'Next';
          nextBtn.onclick = function() {
            currentOffset += pageSize;
            loadMemory();
          };
          nav.appendChild(nextBtn);
        }

        memoryBody.appendChild(nav);
      }
    } catch (e) {
      memoryBody.innerHTML =
        '<span class="text-danger">Failed to load notebook: ' + escapeHtml(e.message) + '</span>';
    }
  };

  // ========================================================================
  // Load recent round summaries
  // ========================================================================

  /**
   * Fetch and display recent notebook entries (rolling context window).
   */
  window.loadRecentMemories = async function() {
    try {
      var data = await api.get('/api/memory/recent?count=10');
      var notes = data.notes || [];

      if (notes.length === 0) {
        recentEl.innerHTML =
          '<div class="empty-state">' +
          '<div class="empty-state-icon">&#x1F4DD;</div>' +
          '<p>No recent notes yet.</p>' +
          '</div>';
        return;
      }

      recentEl.innerHTML = '';

      notes.forEach(function(note) {
        var card = document.createElement('div');
        card.className = 'card mb-sm';
        card.style.padding = 'var(--spacing-md)';

        var time = note.timestamp ? new Date(note.timestamp).toLocaleString() : '';
        var round = note.round || '?';

        card.innerHTML =
          '<div class="flex flex-between flex-center mb-sm">' +
            '<span class="badge badge-primary">Round ' + round + '</span>' +
            '<span class="text-xs text-muted">' + escapeHtml(time) + '</span>' +
          '</div>' +
          '<p class="text-sm">' + escapeHtml(note.content || '') + '</p>';

        recentEl.appendChild(card);
      });
    } catch (e) {
      recentEl.innerHTML =
        '<p class="text-danger text-sm">Failed to load recent notes: ' + escapeHtml(e.message) + '</p>';
    }
  };

  // ========================================================================
  // Utility
  // ========================================================================

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  loadMemory();
  loadRecentMemories();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
