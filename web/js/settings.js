/**
 * Awakener - Settings Page Logic
 * =================================
 * Unified model + API key configuration:
 *   - Provider selection → preset model list → auto-mapped API key
 *   - Agent parameters (interval, max tools, timeout)
 *   - Password change
 *
 * The provider→model→key mapping eliminates the need for users to know
 * environment variable names. They just pick a provider, choose a model,
 * paste their API key, and save. The system figures out the rest.
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // ========================================================================
  // Provider → Model Presets → Env Var Mapping
  // ========================================================================

  /**
   * Registry of supported LLM providers.
   *
   * Each provider defines:
   *   - models:  Array of {value, label} presets for the dropdown
   *   - envKey:  The .env variable name where the API key is stored
   *   - hint:    Help text shown below the API key input
   *
   * The last model option in each list is always "custom" to allow
   * arbitrary model names not in the preset list.
   */
  var PROVIDERS = {
    deepseek: {
      models: [
        { value: 'deepseek/deepseek-chat',     label: 'DeepSeek Chat (V3)' },
        { value: 'deepseek/deepseek-reasoner',  label: 'DeepSeek Reasoner (R1)' },
        { value: '_custom',                     label: '-- Custom --' },
      ],
      envKey: 'DEEPSEEK_API_KEY',
      hint: 'Get your key at platform.deepseek.com',
    },
    openai: {
      models: [
        { value: 'openai/gpt-4o',              label: 'GPT-4o' },
        { value: 'openai/gpt-4o-mini',         label: 'GPT-4o Mini' },
        { value: 'openai/o3-mini',             label: 'o3-mini' },
        { value: '_custom',                     label: '-- Custom --' },
      ],
      envKey: 'OPENAI_API_KEY',
      hint: 'Get your key at platform.openai.com/api-keys',
    },
    anthropic: {
      models: [
        { value: 'anthropic/claude-sonnet-4-20250514',  label: 'Claude Sonnet 4' },
        { value: 'anthropic/claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
        { value: 'anthropic/claude-3-5-haiku-20241022',  label: 'Claude 3.5 Haiku' },
        { value: '_custom',                              label: '-- Custom --' },
      ],
      envKey: 'ANTHROPIC_API_KEY',
      hint: 'Get your key at console.anthropic.com',
    },
    google: {
      models: [
        { value: 'gemini/gemini-2.0-flash',    label: 'Gemini 2.0 Flash' },
        { value: 'gemini/gemini-2.5-pro-preview-06-05', label: 'Gemini 2.5 Pro' },
        { value: '_custom',                     label: '-- Custom --' },
      ],
      envKey: 'GOOGLE_API_KEY',
      hint: 'Get your key at aistudio.google.com/apikey',
    },
    openrouter: {
      models: [
        { value: 'openrouter/deepseek/deepseek-chat-v3-0324', label: 'DeepSeek V3 (via OpenRouter)' },
        { value: 'openrouter/anthropic/claude-sonnet-4',        label: 'Claude Sonnet 4 (via OpenRouter)' },
        { value: '_custom',                                     label: '-- Custom --' },
      ],
      envKey: 'OPENROUTER_API_KEY',
      hint: 'Get your key at openrouter.ai/keys',
    },
    custom: {
      models: [
        { value: '_custom', label: '-- Enter model name below --' },
      ],
      envKey: '_CUSTOM',
      hint: 'Enter the environment variable name and key for your provider',
    },
  };

  // ========================================================================
  // DOM References
  // ========================================================================

  var elProvider   = document.getElementById('model-provider');
  var elPreset     = document.getElementById('model-preset');
  var elModelName  = document.getElementById('model-name');
  var elApiKey     = document.getElementById('model-api-key');
  var elApiBase    = document.getElementById('api-base');
  var elModelHint  = document.getElementById('model-hint');
  var elKeyHint    = document.getElementById('key-hint');

  // Current state
  var currentEnvKey = '';  // The .env variable name for the active provider

  // ========================================================================
  // Provider / Model / Key Logic
  // ========================================================================

  /**
   * Called when the provider dropdown changes.
   * Updates the model preset list and key hint.
   */
  window.onProviderChange = function() {
    var provider = elProvider.value;
    var info = PROVIDERS[provider];
    if (!info) return;

    // Populate model presets
    elPreset.innerHTML = '';
    info.models.forEach(function(m) {
      var opt = document.createElement('option');
      opt.value = m.value;
      opt.textContent = m.label;
      elPreset.appendChild(opt);
    });

    // Show/hide custom model name input
    onPresetChange();

    // Update key hint
    currentEnvKey = info.envKey;
    elKeyHint.textContent = info.hint || '';

    // Load the existing key for this provider (masked)
    loadKeyForProvider(info.envKey);
  };

  /**
   * Called when the model preset dropdown changes.
   * Shows the custom model name input when "_custom" is selected.
   */
  window.onPresetChange = function() {
    var isCustom = (elPreset.value === '_custom');
    if (isCustom) {
      elModelName.classList.remove('hidden');
      elModelName.placeholder = 'e.g. deepseek/deepseek-chat';
      elModelHint.textContent = 'Enter the full LiteLLM model identifier (provider/model-name)';
    } else {
      elModelName.classList.add('hidden');
      elModelName.value = '';
      elModelHint.textContent = '';
    }
  };

  /**
   * Load the masked API key for a given env var name.
   * @param {string} envKey - The environment variable name.
   */
  async function loadKeyForProvider(envKey) {
    if (!envKey || envKey === '_CUSTOM') {
      elApiKey.value = '';
      elApiKey.placeholder = 'sk-...';
      return;
    }

    try {
      var data = await api.get('/api/config/keys');
      var keys = data.keys || {};
      var masked = keys[envKey] || '';
      if (masked) {
        elApiKey.value = masked;
        elApiKey.placeholder = 'Enter new value to update';
      } else {
        elApiKey.value = '';
        elApiKey.placeholder = 'sk-...';
      }
    } catch (e) {
      elApiKey.value = '';
    }
  }

  /**
   * Toggle API key visibility (password ↔ text).
   */
  window.toggleKeyVisibility = function() {
    if (elApiKey.type === 'password') {
      elApiKey.type = 'text';
    } else {
      elApiKey.type = 'password';
    }
  };

  /**
   * Toggle advanced options visibility.
   */
  window.toggleAdvanced = function() {
    var el = document.getElementById('advanced-options');
    var toggle = document.getElementById('advanced-toggle');
    if (el.classList.contains('hidden')) {
      el.classList.remove('hidden');
      toggle.innerHTML = '&#x25BC; <span data-i18n="settings.advanced">Advanced options</span>';
    } else {
      el.classList.add('hidden');
      toggle.innerHTML = '&#x25B6; <span data-i18n="settings.advanced">Advanced options</span>';
    }
  };

  // ========================================================================
  // Save Model Configuration
  // ========================================================================

  /**
   * Save the unified model + API key configuration.
   *
   * Flow:
   *   1. Determine the full model name (from preset or custom input)
   *   2. Save model name to config.yaml via PUT /api/config
   *   3. Save API key to .env via PUT /api/config/keys (if changed)
   */
  window.saveModelConfig = async function() {
    // Determine model name
    var modelName = '';
    if (elPreset.value === '_custom') {
      modelName = elModelName.value.trim();
      if (!modelName) {
        toast('Please enter a model name', 'warning');
        return;
      }
    } else {
      modelName = elPreset.value;
    }

    // Save model to config.yaml
    try {
      await api.put('/api/config', {
        agent: {
          model: modelName,
        }
      });
    } catch (err) {
      toast('Failed to save model: ' + err.message, 'error');
      return;
    }

    // Save API key to .env (if user entered a new value, not masked)
    var keyValue = elApiKey.value.trim();
    if (keyValue && !keyValue.includes('****')) {
      var envKey = currentEnvKey;

      // For custom provider, use the model prefix as env key name
      if (envKey === '_CUSTOM') {
        var prefix = modelName.split('/')[0].toUpperCase().replace(/[^A-Z0-9]/g, '_');
        envKey = prefix + '_API_KEY';
      }

      try {
        var body = {};
        body[envKey] = keyValue;
        await api.put('/api/config/keys', body);
      } catch (err) {
        toast('Model saved, but failed to save API key: ' + err.message, 'error');
        return;
      }
    }

    // Save api_base if provided
    var apiBase = elApiBase.value.trim();
    if (apiBase) {
      try {
        await api.put('/api/config', {
          agent: { api_base: apiBase }
        });
      } catch (e) {
        // Non-critical, ignore
      }
    }

    toast('Configuration saved', 'success');

    // Reload the key display (now masked)
    if (currentEnvKey && currentEnvKey !== '_CUSTOM') {
      loadKeyForProvider(currentEnvKey);
    }
  };

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
   * Detects the current provider from the saved model name and selects
   * the correct provider, preset, and loads the existing API key.
   *
   * @param {Object} config - The full configuration object.
   */
  function populateModelConfig(config) {
    var agent = config.agent || {};
    var model = agent.model || '';  // e.g. "deepseek/deepseek-chat"
    var apiBase = agent.api_base || '';

    // Detect provider from model name
    var detectedProvider = 'custom';
    var providerKeys = Object.keys(PROVIDERS);
    for (var i = 0; i < providerKeys.length; i++) {
      var pKey = providerKeys[i];
      if (pKey === 'custom') continue;
      var info = PROVIDERS[pKey];
      for (var j = 0; j < info.models.length; j++) {
        if (info.models[j].value === model) {
          detectedProvider = pKey;
          break;
        }
      }
      if (detectedProvider !== 'custom') break;
    }

    // If not found in presets, try matching provider prefix
    if (detectedProvider === 'custom' && model.indexOf('/') !== -1) {
      var prefix = model.split('/')[0].toLowerCase();
      // Map common prefixes to providers
      var prefixMap = {
        deepseek: 'deepseek',
        openai: 'openai',
        anthropic: 'anthropic',
        gemini: 'google',
        google: 'google',
        openrouter: 'openrouter',
      };
      if (prefixMap[prefix]) {
        detectedProvider = prefixMap[prefix];
      }
    }

    // Set provider dropdown
    elProvider.value = detectedProvider;

    // Trigger provider change to populate presets
    onProviderChange();

    // Select the matching preset, or fall back to custom
    var found = false;
    for (var k = 0; k < elPreset.options.length; k++) {
      if (elPreset.options[k].value === model) {
        elPreset.value = model;
        found = true;
        break;
      }
    }
    if (!found && model) {
      elPreset.value = '_custom';
      elModelName.value = model;
      elModelName.classList.remove('hidden');
      elModelHint.textContent = 'Current model: ' + model;
    }

    // Set API base
    elApiBase.value = apiBase;
  }

  /**
   * Initialize the settings page: load config, populate forms.
   */
  async function init() {
    try {
      var config = await api.get('/api/config');
      populateModelConfig(config);
      populateAgentParams(config);
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
