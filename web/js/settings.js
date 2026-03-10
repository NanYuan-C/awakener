/**
 * Awakener - Settings Page Logic
 * =================================
 * Model configuration: provider, model name, API URL, API key.
 * Agent parameters (interval, max tools, timeout).
 * Password change.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // ========================================================================
  // Model Configuration
  // ========================================================================

  /**
   * Toggle API key visibility (password ↔ text).
   */
  window.toggleKeyVisibility = function() {
    var el = document.getElementById('model-api-key');
    el.type = (el.type === 'password') ? 'text' : 'password';
  };

  /**
   * Save model configuration.
   *
   * Combines provider + model name into "provider/model-name" for LiteLLM.
   * Derives env var name as PROVIDER_API_KEY and saves to .env.
   * Saves api_base to config.yaml (empty string clears it).
   */
  window.saveModelConfig = async function() {
    var provider  = document.getElementById('model-provider').value.trim();
    var modelName = document.getElementById('model-name').value.trim();
    var apiBase   = document.getElementById('api-base').value.trim();
    var keyValue  = document.getElementById('model-api-key').value.trim();

    if (!provider) {
      toast('Please enter a provider name', 'warning');
      return;
    }
    if (!modelName) {
      toast('Please enter a model name', 'warning');
      return;
    }

    var fullModel = provider + '/' + modelName;

    // Save model and api_base to config.yaml
    try {
      await api.put('/api/config', {
        agent: {
          model: fullModel,
          api_base: apiBase,
        }
      });
    } catch (err) {
      toast('Failed to save model: ' + err.message, 'error');
      return;
    }

    // Save API key to .env (skip if empty or still masked)
    if (keyValue && !keyValue.includes('****')) {
      var envKey = provider.toUpperCase().replace(/[^A-Z0-9]/g, '_') + '_API_KEY';
      try {
        var body = {};
        body[envKey] = keyValue;
        await api.put('/api/config/keys', body);
      } catch (err) {
        toast('Model saved, but failed to save API key: ' + err.message, 'error');
        return;
      }
    }

    toast('Configuration saved', 'success');

    // Reload masked key
    loadModelKey(provider);
  };

  /**
   * Load masked API key for the current provider.
   */
  async function loadModelKey(provider) {
    if (!provider) return;
    var envKey = provider.toUpperCase().replace(/[^A-Z0-9]/g, '_') + '_API_KEY';
    try {
      var data = await api.get('/api/config/keys');
      var masked = (data.keys || {})[envKey] || '';
      var el = document.getElementById('model-api-key');
      el.value = masked;
      el.placeholder = masked ? 'Enter new value to update' : 'sk-...';
    } catch (e) {
      // ignore
    }
  }

  // ========================================================================
  // Agent Parameters
  // ========================================================================

  /**
   * Populate agent parameter form fields from config.
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
  // Snapshot Auditor Configuration
  // ========================================================================

  /**
   * Populate the snapshot model field from config.
   * @param {Object} config - The full configuration object.
   */
  function populateSnapshotConfig(config) {
    var agent = config.agent || {};
    var val = agent.snapshot_model || '';
    // Strip provider prefix so only the model name is shown
    var slashIdx = val.indexOf('/');
    if (slashIdx !== -1) {
      val = val.substring(slashIdx + 1);
    }
    document.getElementById('snapshot-model').value = val;
  }

  /**
   * Save the snapshot auditor model to the server.
   */
  window.saveSnapshotConfig = async function() {
    try {
      await api.put('/api/config', {
        agent: {
          snapshot_model: document.getElementById('snapshot-model').value.trim(),
        }
      });
      toast('Snapshot configuration saved', 'success');
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
  // Initialization
  // ========================================================================

  /**
   * Populate the model section from current config.
   * Splits "provider/model-name" back into the two input fields.
   * @param {Object} config - The full configuration object.
   */
  function populateModelConfig(config) {
    var agent   = config.agent || {};
    var model   = agent.model || '';   // e.g. "deepseek/deepseek-chat"
    var apiBase = agent.api_base || '';

    var slashIdx = model.indexOf('/');
    var provider  = slashIdx !== -1 ? model.substring(0, slashIdx) : model;
    var modelName = slashIdx !== -1 ? model.substring(slashIdx + 1) : '';

    document.getElementById('model-provider').value = provider;
    document.getElementById('model-name').value     = modelName;
    document.getElementById('api-base').value       = apiBase;

    // Load masked key for this provider
    loadModelKey(provider);
  }

  /**
   * Initialize the settings page: load config, populate forms.
   */
  async function init() {
    try {
      var config = await api.get('/api/config');
      populateModelConfig(config);
      populateAgentParams(config);
      populateSnapshotConfig(config);
    } catch (e) {
      toast('Failed to load configuration: ' + e.message, 'error');
    }

    if (typeof i18n !== 'undefined') i18n.apply();
  }

  // ========================================================================
  // Utility
  // ========================================================================

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  init();
})();
