/**
 * Awakener - Prompt Page Logic
 * ================================
 * Editor for persona.md and rules.md, shown as two tabs.
 */

(function() {
  'use strict';

  var currentTab = 'persona';

  // ========================================================================
  // Tab switching
  // ========================================================================

  window.switchTab = function(name) {
    currentTab = name;

    document.getElementById('panel-persona').style.display = name === 'persona' ? '' : 'none';
    document.getElementById('panel-rules').style.display  = name === 'rules'   ? '' : 'none';

    document.getElementById('tab-persona').classList.toggle('active', name === 'persona');
    document.getElementById('tab-rules').classList.toggle('active',   name === 'rules');
  };

  // ========================================================================
  // Load
  // ========================================================================

  async function loadPrompt(name) {
    try {
      var data = await api.get('/api/prompt/' + name);
      document.getElementById(name + '-content').value = data.content || '';
    } catch (e) {
      toast('Failed to load ' + name + ': ' + e.message, 'error');
    }
  }

  // ========================================================================
  // Save
  // ========================================================================

  window.savePrompt = async function(name) {
    var content = document.getElementById(name + '-content').value;
    try {
      await api.put('/api/prompt/' + name, { content: content });
      toast((typeof i18n !== 'undefined' ? i18n.t('prompts.saved') : 'Saved'), 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // -- Init -----------------------------------------------------------------
  loadPrompt('persona');
  loadPrompt('rules');
  if (typeof i18n !== 'undefined') i18n.apply();

})();
