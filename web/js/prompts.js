/**
 * Awakener - Prompt Page Logic
 * ================================
 * Simple editor for the single global agent prompt (prompts/default.md).
 *
 * Handles:
 *   - Loading the current prompt content from /api/prompt
 *   - Saving updated content via PUT /api/prompt
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- DOM references -------------------------------------------------------
  var contentInput = document.getElementById('prompt-content');

  // ========================================================================
  // Load prompt
  // ========================================================================

  async function loadPrompt() {
    try {
      var data = await api.get('/api/prompt');
      contentInput.value = data.content || '';
    } catch (e) {
      toast('Failed to load prompt: ' + e.message, 'error');
    }
  }

  // ========================================================================
  // Save prompt
  // ========================================================================

  window.savePrompt = async function() {
    var content = contentInput.value;

    try {
      await api.put('/api/prompt', { content: content });
      toast(i18n.t('prompts.saved'), 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // -- Init -----------------------------------------------------------------
  loadPrompt();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
