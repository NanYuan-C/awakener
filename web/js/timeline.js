/**
 * Awakener - Timeline Page Logic
 * =================================
 * Handles:
 *   - Loading timeline entries from /api/timeline
 *   - Rendering per-round summaries as timeline items
 *   - Pagination (newer / older)
 *   - Auto-refresh on interval
 *
 * Timeline entries contain: round, timestamp, tools_used, duration, summary.
 * Each entry represents one completed activation round.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- State ----------------------------------------------------------------
  let currentPage   = 0;
  let pageSize      = 50;
  let totalEvents   = 0;

  // -- DOM references -------------------------------------------------------
  const timelineEl   = document.getElementById('timeline');
  const paginationEl = document.getElementById('pagination');
  const pageInfoEl   = document.getElementById('page-info');
  const btnNewer     = document.getElementById('btn-newer');
  const btnOlder     = document.getElementById('btn-older');

  // ========================================================================
  // Load timeline data
  // ========================================================================

  /**
   * Fetch timeline events from the API and render them.
   */
  window.loadTimeline = async function() {
    try {
      var params = new URLSearchParams({
        offset: currentPage * pageSize,
        limit: pageSize,
      });

      const data = await api.get('/api/timeline?' + params.toString());
      totalEvents = data.total || 0;
      renderTimeline(data.events || []);
      updatePagination();
    } catch (e) {
      timelineEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">&#x26A0;</div>' +
        '<p>Failed to load timeline: ' + escapeHtml(e.message) + '</p>' +
        '</div>';
    }
  };

  /**
   * Render timeline entries (one per round) into the DOM.
   * @param {Array} events - Array of timeline entry objects.
   */
  function renderTimeline(events) {
    if (events.length === 0) {
      timelineEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">&#x1F4C5;</div>' +
        '<p>No activation rounds recorded yet.</p>' +
        '</div>';
      return;
    }

    timelineEl.innerHTML = '';

    events.forEach(function(event) {
      var item = document.createElement('div');
      item.className = 'timeline-item';

      var dotClass = 'timeline-dot round';
      var time = formatTime(event.timestamp);
      var round = event.round || '?';
      var tools = event.tools_used || 0;
      var duration = event.duration ? event.duration.toFixed(1) + 's' : '?';
      var summary = event.summary || '';
      var statsHtml =
        '<span class="badge badge-primary">Round ' + round + '</span> ' +
        '<span class="badge badge-info">Tools: ' + tools + '</span> ' +
        '<span class="text-xs text-muted">' + duration + '</span>';

      // Build summary HTML: show first 3 lines, expandable
      var summaryHtml = '';
      if (summary) {
        var lines = summary.split('\n').filter(function(l) { return l.trim(); });
        if (lines.length <= 3) {
          summaryHtml = '<pre class="timeline-summary">' + escapeHtml(summary) + '</pre>';
        } else {
          var previewText = lines.slice(0, 3).join('\n');
          var fullText = summary;
          var itemId = 'tl-summary-' + round;
          summaryHtml =
            '<pre class="timeline-summary" id="' + itemId + '">' + escapeHtml(previewText) + '</pre>' +
            '<pre class="timeline-summary timeline-summary-full" id="' + itemId + '-full" style="display:none">' + escapeHtml(fullText) + '</pre>' +
            '<a href="javascript:void(0)" class="timeline-toggle" onclick="toggleSummary(\'' + itemId + '\')">' +
              '<span data-i18n="timeline.showMore">Show all ' + lines.length + ' lines</span>' +
            '</a>';
        }
      } else {
        summaryHtml = '<p class="text-muted">(no summary)</p>';
      }

      item.innerHTML =
        '<div class="' + dotClass + '"></div>' +
        '<div class="timeline-content">' +
          '<div class="timeline-time flex flex-between flex-center">' +
            '<div>' + statsHtml + ' &mdash; ' + escapeHtml(time) + '</div>' +
            '<button class="btn btn-sm btn-danger" onclick="deleteTimelineEntry(' + round + ')" title="Delete">' +
              '&#x1F5D1;' +
            '</button>' +
          '</div>' +
          '<div class="timeline-body">' + summaryHtml + '</div>' +
        '</div>';

      timelineEl.appendChild(item);
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
    currentPage = 0;
    loadTimeline();
  };

  // ========================================================================
  // Pagination
  // ========================================================================

  function updatePagination() {
    var totalPages = Math.ceil(totalEvents / pageSize);
    if (totalPages <= 1) {
      paginationEl.style.display = 'none';
      return;
    }

    paginationEl.style.display = '';
    pageInfoEl.textContent = 'Page ' + (currentPage + 1) + ' of ' + totalPages +
                             ' (' + totalEvents + ' events)';
    btnNewer.disabled = currentPage === 0;
    btnOlder.disabled = currentPage >= totalPages - 1;
  }

  /**
   * Navigate to a newer or older page.
   * @param {string} direction - 'newer' or 'older'.
   */
  window.loadPage = function(direction) {
    if (direction === 'newer' && currentPage > 0) {
      currentPage--;
    } else if (direction === 'older') {
      currentPage++;
    }
    loadTimeline();
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

  /**
   * Map event type to badge CSS class.
   * @param {string} type - The event type.
   * @returns {string} Badge class suffix.
   */
  function typeBadgeClass(type) {
    if (type === 'round' || type === 'round_start') return 'primary';
    if (type === 'tool' || type === 'tool_call')    return 'info';
    if (type === 'thought')                          return 'warning';
    if (type === 'error')                            return 'danger';
    return 'primary';
  }

  /**
   * Toggle between 3-line preview and full summary.
   * @param {string} id - The preview element ID.
   */
  window.toggleSummary = function(id) {
    var preview = document.getElementById(id);
    var full = document.getElementById(id + '-full');
    var link = preview ? preview.parentElement.querySelector('.timeline-toggle') : null;
    if (!preview || !full) return;

    if (full.style.display === 'none') {
      preview.style.display = 'none';
      full.style.display = '';
      if (link) link.innerHTML = '<span data-i18n="timeline.showLess">Collapse</span>';
    } else {
      preview.style.display = '';
      full.style.display = 'none';
      if (link) link.innerHTML = '<span data-i18n="timeline.showMore">Show more</span>';
    }
  };

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

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  loadTimeline();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
