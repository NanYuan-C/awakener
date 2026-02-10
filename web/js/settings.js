/**
 * Awakener - Settings Page Logic
 * =================================
 * Handles:
 *   - Loading current configuration from /api/config
 *   - Saving model configuration (provider, model name, api base)
 *   - Managing API keys (list, add, update, delete)
 *   - Saving agent parameters (interval, max tools, timeout)
 *   - Changing the admin password
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // ========================================================================
  // Load configuration on page init
  // ========================================================================

  async function init() {
    try {
      const config = await api.get('/api/config');
      populateModelConfig(config);
      populateAgentParams(config);
    } catch (e) {
      toast('Failed to load configuration: ' + e.message, 'error');
    }

    try {
      await loadApiKeys();
    } catch (e) {
      toast('Failed to load API keys: ' + e.message, 'error');
    }

    if (typeof i18n !== 'undefined') i18n.apply();
  }

  // ========================================================================
  // Model Configuration
  // ========================================================================

  /**
   * Populate the model configuration form fields.
   * @param {Object} config - The full configuration object.
   */
  function populateModelConfig(config) {
    const model = config.model || {};

    // Detect provider from model name or separate field
    var provider = model.provider || '';
    if (!provider && model.name) {
      if (model.name.startsWith('deepseek')) provider = 'deepseek';
      else if (model.name.startsWith('gpt') || model.name.startsWith('o1') || model.name.startsWith('o3')) provider = 'openai';
      else if (model.name.startsWith('claude')) provider = 'anthropic';
      else provider = 'custom';
    }

    document.getElementById('model-provider').value = provider || 'deepseek';
    document.getElementById('model-name').value = model.name || '';
    document.getElementById('api-base').value = model.api_base || '';
  }

  /**
   * Save model configuration to the server.
   */
  window.saveModelConfig = async function() {
    try {
      await api.put('/api/config', {
        model: {
          provider: document.getElementById('model-provider').value,
          name: document.getElementById('model-name').value,
          api_base: document.getElementById('api-base').value || null,
        }
      });
      toast('Model configuration saved', 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // API Keys
  // ========================================================================

  /**
   * Load and display API keys (masked).
   */
  async function loadApiKeys() {
    const data = await api.get('/api/config/keys');
    const container = document.getElementById('api-keys-list');
    container.innerHTML = '';

    var keys = data.keys || {};
    var names = Object.keys(keys);

    if (names.length === 0) {
      container.innerHTML = '<p class="text-sm text-muted">No API keys configured yet.</p>';
      return;
    }

    names.forEach(function(name) {
      var row = document.createElement('div');
      row.className = 'key-row';
      row.innerHTML =
        '<code class="text-sm" style="min-width:180px;">' + escapeHtml(name) + '</code>' +
        '<input type="text" class="form-control" value="' + escapeHtml(keys[name]) + '" ' +
        'data-key-name="' + escapeHtml(name) + '" placeholder="Enter new value to update">' +
        '<button class="btn btn-sm btn-primary" onclick="saveApiKey(\'' + escapeHtml(name) + '\')">Save</button>' +
        '<button class="btn btn-sm btn-danger" onclick="deleteApiKey(\'' + escapeHtml(name) + '\')">Delete</button>';
      container.appendChild(row);
    });
  }

  /**
   * Save an existing API key with a new value.
   * @param {string} name - The key name to save.
   */
  window.saveApiKey = async function(name) {
    var input = document.querySelector('input[data-key-name="' + name + '"]');
    if (!input) return;

    var value = input.value.trim();
    if (!value || value.includes('****')) {
      toast('Enter a new key value to save (not the masked value)', 'warning');
      return;
    }

    try {
      var body = {};
      body[name] = value;
      await api.put('/api/config/keys', body);
      toast('API key saved: ' + name, 'success');
      await loadApiKeys();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  /**
   * Add a new API key.
   */
  window.addApiKey = async function() {
    var nameInput = document.getElementById('new-key-name');
    var valueInput = document.getElementById('new-key-value');
    var name = nameInput.value.trim().toUpperCase();
    var value = valueInput.value.trim();

    if (!name || !value) {
      toast('Please enter both a key name and value', 'warning');
      return;
    }

    try {
      var body = {};
      body[name] = value;
      await api.put('/api/config/keys', body);
      toast('API key added: ' + name, 'success');
      nameInput.value = '';
      valueInput.value = '';
      await loadApiKeys();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  /**
   * Delete an API key.
   * @param {string} name - The key name to delete.
   */
  window.deleteApiKey = async function(name) {
    if (!confirm('Delete API key "' + name + '"?')) return;

    try {
      await api.delete('/api/config/keys/' + encodeURIComponent(name));
      toast('API key deleted: ' + name, 'success');
      await loadApiKeys();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Agent Parameters
  // ========================================================================

  /**
   * Populate agent parameter form fields.
   * @param {Object} config - The full configuration object.
   */
  function populateAgentParams(config) {
    var agent = config.agent || {};
    document.getElementById('interval').value    = agent.interval ?? 30;
    document.getElementById('max-tools').value    = agent.max_tool_calls ?? 20;
    document.getElementById('tool-timeout').value = agent.shell_timeout ?? 30;
  }

  /**
   * Save agent parameters to the server.
   */
  window.saveAgentParams = async function() {
    try {
      await api.put('/api/config', {
        agent: {
          interval: parseInt(document.getElementById('interval').value, 10),
          max_tool_calls: parseInt(document.getElementById('max-tools').value, 10),
          shell_timeout: parseInt(document.getElementById('tool-timeout').value, 10),
        }
      });
      toast('Agent parameters saved', 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Password Change
  // ========================================================================

  /**
   * Change the admin password.
   */
  window.changePassword = async function() {
    var current = document.getElementById('current-password').value;
    var newPwd  = document.getElementById('new-password').value;

    if (!current || !newPwd) {
      toast('Please fill in both fields', 'warning');
      return;
    }

    if (newPwd.length < 4) {
      toast('New password must be at least 4 characters', 'warning');
      return;
    }

    try {
      await api.post('/api/auth/password', {
        current_password: current,
        new_password: newPwd,
      });
      toast('Password changed successfully', 'success');
      document.getElementById('current-password').value = '';
      document.getElementById('new-password').value = '';
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Utility
  // ========================================================================

  /**
   * Escape HTML special characters to prevent XSS.
   * @param {string} str - The input string.
   * @returns {string} Escaped string.
   */
  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  init();
})();
