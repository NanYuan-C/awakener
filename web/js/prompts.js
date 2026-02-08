/**
 * Awakener - Prompts (Persona) Page Logic
 * ==========================================
 * Handles:
 *   - Loading available persona prompts from /api/prompts
 *   - Displaying persona cards with preview text
 *   - Selecting the active persona
 *   - Creating, editing, and deleting persona files
 *   - Modal for editing prompt content (Markdown)
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- State ----------------------------------------------------------------
  let currentPrompts = [];
  let activePrompt = '';
  let editingPrompt = null;  // null = creating new, string = editing existing

  // -- DOM references -------------------------------------------------------
  const listEl    = document.getElementById('prompt-list');
  const modalEl   = document.getElementById('prompt-modal');
  const titleEl   = document.getElementById('modal-title');
  const filenameInput = document.getElementById('prompt-filename');
  const contentInput  = document.getElementById('prompt-content');

  // ========================================================================
  // Load prompts list
  // ========================================================================

  async function loadPrompts() {
    try {
      const data = await api.get('/api/prompts');
      currentPrompts = data.prompts || [];
      activePrompt = data.active || '';
      renderPromptList();
    } catch (e) {
      toast('Failed to load personas: ' + e.message, 'error');
    }
  }

  /**
   * Render the persona cards grid.
   */
  function renderPromptList() {
    if (currentPrompts.length === 0) {
      listEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">&#x1F3AD;</div>' +
        '<p>No persona prompts found. Create one to get started.</p>' +
        '</div>';
      return;
    }

    listEl.innerHTML = '';

    currentPrompts.forEach(function(prompt) {
      var card = document.createElement('div');
      card.className = 'prompt-card' + (prompt.name === activePrompt ? ' active' : '');

      // Extract first 3 lines as preview
      var preview = (prompt.preview || prompt.content || '').substring(0, 150);
      if (preview.length >= 150) preview += '...';

      card.innerHTML =
        '<h4>' + escapeHtml(prompt.name) + '</h4>' +
        (prompt.name === activePrompt
          ? '<span class="badge badge-success mb-sm">Active</span>'
          : '') +
        '<p>' + escapeHtml(preview) + '</p>' +
        '<div class="prompt-card-footer">' +
          '<button class="btn btn-sm btn-outline" onclick="editPrompt(\'' + escapeHtml(prompt.name) + '\')">Edit</button>' +
          '<div class="flex gap-sm">' +
            (prompt.name !== activePrompt
              ? '<button class="btn btn-sm btn-primary" onclick="activatePrompt(\'' + escapeHtml(prompt.name) + '\')">Use</button>'
              : '') +
            '<button class="btn btn-sm btn-danger" onclick="deletePrompt(\'' + escapeHtml(prompt.name) + '\')">Delete</button>' +
          '</div>' +
        '</div>';

      listEl.appendChild(card);
    });
  }

  // ========================================================================
  // Activate a persona
  // ========================================================================

  /**
   * Set a persona as the active one.
   * @param {string} name - The filename of the persona to activate.
   */
  window.activatePrompt = async function(name) {
    try {
      await api.put('/api/config', {
        agent: { persona: name }
      });
      activePrompt = name;
      renderPromptList();
      toast('Persona activated: ' + name, 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Create / Edit modal
  // ========================================================================

  /**
   * Open the modal for creating a new persona.
   */
  window.showCreateModal = function() {
    editingPrompt = null;
    titleEl.textContent = 'New Persona';
    filenameInput.value = '';
    filenameInput.disabled = false;
    contentInput.value = '';
    modalEl.classList.remove('hidden');
  };

  /**
   * Open the modal for editing an existing persona.
   * @param {string} name - The filename of the persona to edit.
   */
  window.editPrompt = async function(name) {
    editingPrompt = name;
    titleEl.textContent = 'Edit: ' + name;
    filenameInput.value = name;
    filenameInput.disabled = true;  // Can't rename files via this modal
    contentInput.value = '';

    // Load full content
    try {
      const data = await api.get('/api/prompts/' + encodeURIComponent(name));
      contentInput.value = data.content || '';
    } catch (e) {
      toast('Failed to load prompt: ' + e.message, 'error');
    }

    modalEl.classList.remove('hidden');
  };

  /**
   * Close the edit modal.
   */
  window.closeModal = function() {
    modalEl.classList.add('hidden');
  };

  /**
   * Save the prompt (create or update).
   */
  window.savePrompt = async function() {
    var filename = filenameInput.value.trim();
    var content  = contentInput.value;

    if (!filename) {
      toast('Please enter a filename', 'warning');
      return;
    }

    // Ensure .md extension
    if (!filename.endsWith('.md')) {
      filename += '.md';
    }

    try {
      await api.put('/api/prompts/' + encodeURIComponent(filename), {
        content: content,
      });
      toast('Persona saved: ' + filename, 'success');
      closeModal();
      await loadPrompts();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Delete a persona
  // ========================================================================

  /**
   * Delete a persona file.
   * @param {string} name - The filename of the persona to delete.
   */
  window.deletePrompt = async function(name) {
    if (!confirm('Delete persona "' + name + '"? This cannot be undone.')) return;

    try {
      await api.delete('/api/prompts/' + encodeURIComponent(name));
      toast('Persona deleted: ' + name, 'success');
      await loadPrompts();
    } catch (err) {
      toast(err.message, 'error');
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

  // Close modal on overlay click
  modalEl.addEventListener('click', function(e) {
    if (e.target === modalEl) closeModal();
  });

  // Close modal on Escape key
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
  });

  // -- Init -----------------------------------------------------------------
  loadPrompts();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
