/**
 * Awakener - Activity Feed Page Logic
 * =====================================
 * Combined activity feed with timeline-style presentation:
 *   - Activity entries from feed.jsonl with tag filtering and lazy loading
 *   - Timeline-style vertical line and dot nodes on the left
 *   - Click "View Details" to open a modal with full round timeline data
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- State ------------------------------------------------------------------
  var allEntries = [];
  var displayedCount = 0;
  var currentFilter = 'all';
  var PAGE_SIZE = 20;
  var currentModalRound = null;

  // -- Tag metadata -----------------------------------------------------------
  var TAG_META = {
    milestone:   { icon: '&#x1F3C6;', label: 'Milestone',   cls: 'tag-milestone',   dot: 'dot-milestone' },
    creation:    { icon: '&#x1F528;', label: 'Creation',     cls: 'tag-creation',    dot: 'dot-creation' },
    exploration: { icon: '&#x1F50D;', label: 'Exploration',  cls: 'tag-exploration', dot: 'dot-exploration' },
    fix:         { icon: '&#x1F527;', label: 'Fix',          cls: 'tag-fix',         dot: 'dot-fix' },
    discovery:   { icon: '&#x1F4A1;', label: 'Discovery',    cls: 'tag-discovery',   dot: 'dot-discovery' },
    routine:     { icon: '&#x1F504;', label: 'Routine',      cls: 'tag-routine',     dot: 'dot-routine' },
  };

  // -- Helpers ----------------------------------------------------------------

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatTime(ts) {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleString();
    } catch (e) {
      return ts;
    }
  }

  function renderTag(tag) {
    var meta = TAG_META[tag] || { icon: '', label: tag, cls: 'tag-default' };
    return '<span class="feed-tag ' + meta.cls + '">' +
           meta.icon + ' ' + escapeHtml(meta.label) + '</span>';
  }

  /**
   * Pick the dot color class from an entry's tags.
   * Uses the first non-routine tag; falls back to 'dot-routine'.
   */
  function getDotClass(tags) {
    if (!tags || !tags.length) return 'dot-routine';
    for (var i = 0; i < tags.length; i++) {
      if (tags[i] !== 'routine' && TAG_META[tags[i]]) {
        return TAG_META[tags[i]].dot;
      }
    }
    return 'dot-routine';
  }

  // -- Filtering --------------------------------------------------------------

  function getFiltered() {
    if (currentFilter === 'all') return allEntries;
    if (currentFilter === 'notable') {
      return allEntries.filter(function(e) {
        return !e.tags || e.tags.indexOf('routine') === -1;
      });
    }
    return allEntries.filter(function(e) {
      return e.tags && e.tags.indexOf(currentFilter) !== -1;
    });
  }

  // =========================================================================
  // Rendering — Feed List
  // =========================================================================

  function renderEntries(entries, container) {
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var tagsHtml = '';
      if (e.tags && e.tags.length) {
        tagsHtml = e.tags.map(renderTag).join(' ');
      }

      var isRoutine = e.tags && e.tags.indexOf('routine') !== -1;
      var cardClass = 'feed-card' + (isRoutine ? ' feed-card-routine' : '');
      var dotClass = 'feed-timeline-dot ' + getDotClass(e.tags);
      var round = e.round || '?';

      var html =
        '<div class="feed-timeline-item">' +
          '<div class="' + dotClass + '"></div>' +
          '<div class="' + cardClass + '">' +
            '<div class="feed-header">' +
              '<span class="feed-round">Round ' + round + '</span>' +
              '<span class="feed-time">' + escapeHtml(formatTime(e.timestamp)) + '</span>' +
            '</div>' +
            '<div class="feed-content">' + escapeHtml(e.content) + '</div>' +
            '<div class="feed-footer">' +
              '<div class="feed-tags">' + tagsHtml + '</div>' +
              '<a href="javascript:void(0)" class="feed-detail-link" onclick="openRoundDetail(' + round + ')">' +
                '<span data-i18n="feed.viewDetails">View Details</span> &rsaquo;' +
              '</a>' +
            '</div>' +
          '</div>' +
        '</div>';

      var div = document.createElement('div');
      div.innerHTML = html;
      container.appendChild(div.firstChild);
    }
  }

  function renderPage(reset) {
    var container = document.getElementById('feed-list');
    var loadMore = document.getElementById('feed-load-more');

    if (reset) {
      container.innerHTML = '';
      displayedCount = 0;
    }

    var filtered = getFiltered();

    if (filtered.length === 0) {
      container.className = '';
      container.innerHTML =
        '<div class="empty-state">' +
          '<div class="empty-state-icon">&#x1F4E1;</div>' +
          '<p data-i18n="feed.noData">No activities found</p>' +
        '</div>';
      loadMore.style.display = 'none';
      return;
    }

    container.className = 'feed-timeline';
    var page = filtered.slice(displayedCount, displayedCount + PAGE_SIZE);
    renderEntries(page, container);
    displayedCount += page.length;

    loadMore.style.display = (displayedCount < filtered.length) ? '' : 'none';

    if (typeof i18n !== 'undefined') i18n.apply();
  }

  // =========================================================================
  // API — Load Feed
  // =========================================================================

  window.loadFeed = async function() {
    try {
      var data = await api.get('/api/feed');
      allEntries = data.entries || [];
      renderPage(true);
    } catch (e) {
      var container = document.getElementById('feed-list');
      container.className = '';
      container.innerHTML =
        '<div class="empty-state">' +
          '<div class="empty-state-icon">&#x1F4E1;</div>' +
          '<p>Failed to load feed: ' + escapeHtml(e.message) + '</p>' +
        '</div>';
    }
  };

  window.loadMoreFeed = function() {
    renderPage(false);
  };

  window.setFeedFilter = function(filter) {
    currentFilter = filter;

    var btns = document.querySelectorAll('.filter-btn');
    for (var i = 0; i < btns.length; i++) {
      var btn = btns[i];
      if (btn.getAttribute('data-filter') === filter) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }

    renderPage(true);
  };

  // =========================================================================
  // Round Detail Modal
  // =========================================================================

  /**
   * Open the modal and fetch full timeline data for a round.
   */
  window.openRoundDetail = async function(round) {
    currentModalRound = round;
    var modal = document.getElementById('round-modal');
    var title = document.getElementById('round-modal-title');
    var body = document.getElementById('round-modal-body');
    var footer = document.getElementById('round-modal-footer');

    title.textContent = 'Round ' + round;
    body.innerHTML = '<div class="text-center text-muted" style="padding:2rem">Loading...</div>';
    footer.style.display = 'none';
    modal.style.display = '';

    try {
      var data = await api.get('/api/timeline/' + round);
      renderRoundDetail(data, title, body);
      footer.style.display = '';
    } catch (e) {
      body.innerHTML =
        '<div class="empty-state">' +
          '<p data-i18n="feed.noRoundData">No timeline data available for this round.</p>' +
        '</div>';
    }

    if (typeof i18n !== 'undefined') i18n.apply();
  };

  window.closeRoundModal = function() {
    document.getElementById('round-modal').style.display = 'none';
    currentModalRound = null;
  };

  /**
   * Delete the current round's timeline data from inside the modal.
   * Feed entries are independent and remain untouched.
   */
  window.deleteRoundFromModal = async function() {
    if (!currentModalRound) return;
    if (!confirm('Delete Round ' + currentModalRound + '?\nThis will remove the timeline and log data for this round.')) return;

    try {
      await api.delete('/api/timeline/' + currentModalRound);
      if (typeof toast === 'function') toast('Round ' + currentModalRound + ' deleted', 'success');
      closeRoundModal();
    } catch (e) {
      if (typeof toast === 'function') toast('Failed to delete: ' + e.message, 'error');
    }
  };

  /**
   * Render the timeline detail: stats in header, full summary in body.
   */
  function renderRoundDetail(entry, titleContainer, bodyContainer) {
    var round = entry.round || '?';
    var tools = entry.tools_used || 0;
    var duration = entry.duration ? entry.duration.toFixed(1) + 's' : '?';
    var time = formatTime(entry.timestamp);
    var summary = entry.summary || '';

    // Header: Round number + stats
    titleContainer.innerHTML =
      'Round ' + round +
      '<div class="modal-header-stats">' +
        '<span class="badge badge-info">Tools: ' + tools + '</span> ' +
        '<span class="badge">' + escapeHtml(duration) + '</span> ' +
        '<span class="text-xs text-muted">' + escapeHtml(time) + '</span>' +
      '</div>';

    // Body: full summary (no collapse/expand)
    if (!summary) {
      bodyContainer.innerHTML = '<p class="text-muted">(no content)</p>';
    } else {
      bodyContainer.innerHTML = '<pre class="timeline-summary">' + escapeHtml(summary) + '</pre>';
    }
  }

  // -- Keyboard: ESC closes modal -------------------------------------------
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeRoundModal();
  });

  // -- Init -----------------------------------------------------------------
  loadFeed();

})();
