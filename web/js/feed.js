/**
 * Awakener - Activity Feed Page Logic
 * =====================================
 * Loads and displays the agent's activity feed with tag filtering
 * and lazy loading.
 */

(function() {
  'use strict';

  // -- State ------------------------------------------------------------------
  var allEntries = [];      // All loaded entries (newest first)
  var displayedCount = 0;   // How many are currently rendered
  var currentFilter = 'all';
  var PAGE_SIZE = 20;

  // -- Tag metadata -----------------------------------------------------------
  var TAG_META = {
    milestone:   { icon: '&#x1F3C6;', label: 'Milestone',   cls: 'tag-milestone' },
    creation:    { icon: '&#x1F528;', label: 'Creation',     cls: 'tag-creation' },
    exploration: { icon: '&#x1F50D;', label: 'Exploration',  cls: 'tag-exploration' },
    fix:         { icon: '&#x1F527;', label: 'Fix',          cls: 'tag-fix' },
    discovery:   { icon: '&#x1F4A1;', label: 'Discovery',    cls: 'tag-discovery' },
    routine:     { icon: '&#x1F504;', label: 'Routine',      cls: 'tag-routine' },
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
      var d = new Date(ts);
      return d.toLocaleString();
    } catch (e) {
      return ts;
    }
  }

  function renderTag(tag) {
    var meta = TAG_META[tag] || { icon: '', label: tag, cls: 'tag-default' };
    return '<span class="feed-tag ' + meta.cls + '">' +
           meta.icon + ' ' + escapeHtml(meta.label) + '</span>';
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

  // -- Rendering --------------------------------------------------------------

  function renderEntries(entries, container) {
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var tagsHtml = '';
      if (e.tags && e.tags.length) {
        tagsHtml = e.tags.map(renderTag).join(' ');
      }

      var isRoutine = e.tags && e.tags.indexOf('routine') !== -1;
      var cardClass = 'feed-card' + (isRoutine ? ' feed-card-routine' : '');

      var html =
        '<div class="' + cardClass + '">' +
          '<div class="feed-header">' +
            '<span class="feed-round">Round ' + (e.round || '?') + '</span>' +
            '<span class="feed-time">' + escapeHtml(formatTime(e.timestamp)) + '</span>' +
          '</div>' +
          '<div class="feed-content">' + escapeHtml(e.content) + '</div>' +
          '<div class="feed-tags">' + tagsHtml + '</div>' +
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
      container.innerHTML =
        '<div class="empty-state">' +
          '<div class="empty-state-icon">&#x1F4E1;</div>' +
          '<p>No activities found</p>' +
        '</div>';
      loadMore.style.display = 'none';
      return;
    }

    var page = filtered.slice(displayedCount, displayedCount + PAGE_SIZE);
    renderEntries(page, container);
    displayedCount += page.length;

    loadMore.style.display = (displayedCount < filtered.length) ? '' : 'none';
  }

  // -- API --------------------------------------------------------------------

  window.loadFeed = async function(reset) {
    try {
      var data = await api.get('/api/feed');
      allEntries = data.entries || [];
      renderPage(true);
    } catch (e) {
      var container = document.getElementById('feed-list');
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

    // Update active button
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

  // -- Init -------------------------------------------------------------------
  loadFeed(true);

})();
