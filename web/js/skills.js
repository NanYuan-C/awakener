/**
 * Awakener - Skills Page Logic
 * ================================
 * Manages agent skills: list, view, create, toggle, delete.
 *
 * Each skill is a directory under data/skills/ containing a SKILL.md
 * file with YAML frontmatter (name, description, version, tags).
 *
 * Depends on: api.js (global `api` object), i18n.js (global `i18n` object)
 */

(function() {
  'use strict';

  // -- State ----------------------------------------------------------------
  var currentSkills = [];
  var editingSkill = null; // null = creating new, string = editing existing

  // -- DOM references -------------------------------------------------------
  var listEl       = document.getElementById('skill-list');
  var modalEl      = document.getElementById('skill-modal');
  var titleEl      = document.getElementById('modal-title');
  var nameInput    = document.getElementById('skill-name');
  var nameGroup    = document.getElementById('name-group');
  var contentInput = document.getElementById('skill-content');
  var filesInfo    = document.getElementById('skill-files-info');
  var refsInfo     = document.getElementById('skill-refs-info');
  var scriptsInfo  = document.getElementById('skill-scripts-info');

  // ========================================================================
  // Load skills list
  // ========================================================================

  async function loadSkills() {
    try {
      var data = await api.get('/api/skills');
      currentSkills = data.skills || [];
      renderSkillList();
    } catch (e) {
      toast('Failed to load skills: ' + e.message, 'error');
    }
  }

  /**
   * Render the skills card grid.
   */
  function renderSkillList() {
    if (currentSkills.length === 0) {
      listEl.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">&#x1F9E9;</div>' +
        '<p>' + t('skills.no_data') + '</p>' +
        '</div>';
      return;
    }

    listEl.innerHTML = '';

    currentSkills.forEach(function(skill) {
      var card = document.createElement('div');
      card.className = 'skill-card' + (skill.enabled ? '' : ' disabled');

      var tags = '';
      if (skill.tags && skill.tags.length > 0) {
        tags = '<div class="skill-tags">';
        skill.tags.forEach(function(tag) {
          tags += '<span class="skill-tag">' + escapeHtml(tag) + '</span>';
        });
        tags += '</div>';
      }

      var badges = '';
      if (skill.has_scripts) badges += '<span class="badge badge-info">scripts</span> ';
      if (skill.has_refs) badges += '<span class="badge badge-info">refs</span> ';

      var statusBadge = skill.enabled
        ? '<span class="badge badge-success">' + t('skills.enabled') + '</span>'
        : '<span class="badge badge-muted">' + t('skills.disabled') + '</span>';

      card.innerHTML =
        '<div class="skill-card-header">' +
          '<h4>' + escapeHtml(skill.title || skill.name) + '</h4>' +
          statusBadge +
        '</div>' +
        '<p class="skill-desc">' + escapeHtml(skill.description || '') + '</p>' +
        tags +
        '<div class="skill-card-meta">' +
          (skill.version ? '<span class="text-sm text-muted">v' + escapeHtml(skill.version) + '</span>' : '') +
          '<span>' + badges + '</span>' +
        '</div>' +
        '<div class="skill-card-footer">' +
          '<button class="btn btn-sm btn-outline" onclick="viewSkill(\'' + escapeHtml(skill.name) + '\')">' +
            t('skills.edit') +
          '</button>' +
          '<div class="flex gap-sm">' +
            '<button class="btn btn-sm ' + (skill.enabled ? 'btn-warning' : 'btn-primary') + '" ' +
              'onclick="toggleSkill(\'' + escapeHtml(skill.name) + '\')">' +
              (skill.enabled ? t('skills.disable') : t('skills.enable')) +
            '</button>' +
            '<button class="btn btn-sm btn-danger" onclick="deleteSkill(\'' + escapeHtml(skill.name) + '\')">' +
              t('skills.delete') +
            '</button>' +
          '</div>' +
        '</div>';

      listEl.appendChild(card);
    });
  }

  // ========================================================================
  // View / Edit skill
  // ========================================================================

  window.viewSkill = async function(name) {
    editingSkill = name;
    titleEl.textContent = name;
    nameInput.value = name;
    nameGroup.style.display = 'none'; // Hide name input in edit mode
    contentInput.value = '';
    filesInfo.classList.add('hidden');

    try {
      var data = await api.get('/api/skills/' + encodeURIComponent(name));
      contentInput.value = data.content || '';

      // Show file info
      if (data.references.length > 0 || data.scripts.length > 0) {
        filesInfo.classList.remove('hidden');
        refsInfo.textContent = data.references.length > 0
          ? t('skills.references') + ': ' + data.references.join(', ')
          : '';
        scriptsInfo.textContent = data.scripts.length > 0
          ? t('skills.scripts') + ': ' + data.scripts.join(', ')
          : '';
      }
    } catch (e) {
      toast('Failed to load skill: ' + e.message, 'error');
    }

    modalEl.classList.remove('hidden');
  };

  // ========================================================================
  // Create skill
  // ========================================================================

  window.showCreateModal = function() {
    editingSkill = null;
    titleEl.textContent = t('skills.createTitle');
    nameInput.value = '';
    nameGroup.style.display = ''; // Show name input in create mode
    contentInput.value =
      '---\nname: My Skill\ndescription: What this skill does\n' +
      "version: '1.0'\ntags: [example]\n---\n\n# Instructions\n\n";
    filesInfo.classList.add('hidden');
    modalEl.classList.remove('hidden');
  };

  // ========================================================================
  // Save skill
  // ========================================================================

  window.saveSkill = async function() {
    var name = editingSkill || nameInput.value.trim();
    var content = contentInput.value;

    if (!name) {
      toast(t('skills.nameRequired'), 'warning');
      return;
    }

    // Validate name: lowercase letters, numbers, hyphens
    if (!editingSkill && !/^[a-z0-9][a-z0-9-]*$/.test(name)) {
      toast(t('skills.nameInvalid'), 'warning');
      return;
    }

    try {
      await api.put('/api/skills/' + encodeURIComponent(name), {
        content: content,
      });
      toast(t('skills.saved') + ': ' + name, 'success');
      closeModal();
      await loadSkills();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Toggle skill
  // ========================================================================

  window.toggleSkill = async function(name) {
    try {
      var result = await api.put('/api/skills/' + encodeURIComponent(name) + '/toggle', {});
      var status = result.enabled ? t('skills.enabled') : t('skills.disabled');
      toast(name + ': ' + status, 'success');
      await loadSkills();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Delete skill
  // ========================================================================

  window.deleteSkill = async function(name) {
    if (!confirm(t('skills.confirmDelete').replace('{name}', name))) return;

    try {
      await api.delete('/api/skills/' + encodeURIComponent(name));
      toast(t('skills.deleted') + ': ' + name, 'success');
      await loadSkills();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  // ========================================================================
  // Upload skill folder
  // ========================================================================

  /**
   * Trigger the hidden folder input.
   */
  window.triggerUpload = function() {
    var input = document.getElementById('folder-input');
    input.value = ''; // Reset so the same folder can be re-selected
    input.click();
  };

  /**
   * Handle folder selection from the file input.
   * Reads all files, validates, and uploads to the backend.
   *
   * @param {HTMLInputElement} input - The file input element.
   */
  window.handleFolderUpload = async function(input) {
    var fileList = input.files;
    if (!fileList || fileList.length === 0) return;

    // Determine the skill directory name from the first file's path.
    // webkitRelativePath format: "folder-name/SKILL.md" or "folder-name/sub/file"
    var firstPath = fileList[0].webkitRelativePath || '';
    var skillName = firstPath.split('/')[0];

    if (!skillName) {
      toast(t('skills.uploadError'), 'error');
      return;
    }

    // Check for duplicate name against loaded skills
    var exists = currentSkills.some(function(s) { return s.name === skillName; });
    if (exists) {
      toast(t('skills.uploadDuplicate').replace('{name}', skillName), 'error');
      return;
    }

    // Read all files and build the payload
    var files = [];
    var hasSkillMd = false;
    var skillMdContent = '';

    for (var i = 0; i < fileList.length; i++) {
      var file = fileList[i];
      var relPath = file.webkitRelativePath || file.name;

      // Strip the top-level directory name to get the relative path within the skill
      var parts = relPath.split('/');
      parts.shift(); // Remove top-level dir
      var innerPath = parts.join('/');

      if (!innerPath) continue;

      // Read file content as text
      try {
        var content = await readFileAsText(file);
        files.push({ path: innerPath, content: content });

        if (innerPath === 'SKILL.md') {
          hasSkillMd = true;
          skillMdContent = content;
        }
      } catch (err) {
        // Skip binary files that can't be read as text
        console.warn('Skipping file (binary?):', innerPath);
      }
    }

    // Validate: SKILL.md must exist
    if (!hasSkillMd) {
      toast(t('skills.uploadNoSkillMd'), 'error');
      return;
    }

    // Validate: frontmatter must have name and description
    var validation = validateSkillMd(skillMdContent);
    if (validation) {
      toast(validation, 'error');
      return;
    }

    // Upload to backend
    try {
      var result = await api.post('/api/skills/upload', {
        name: skillName,
        files: files,
      });
      toast(t('skills.uploadSuccess').replace('{name}', skillName)
            .replace('{count}', result.files || files.length), 'success');
      await loadSkills();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  /**
   * Read a File object as text.
   * @param {File} file
   * @returns {Promise<string>}
   */
  function readFileAsText(file) {
    return new Promise(function(resolve, reject) {
      var reader = new FileReader();
      reader.onload = function() { resolve(reader.result); };
      reader.onerror = function() { reject(reader.error); };
      reader.readAsText(file);
    });
  }

  /**
   * Validate SKILL.md content: must have frontmatter with name & description.
   * @param {string} content - The SKILL.md file content.
   * @returns {string|null} Error message, or null if valid.
   */
  function validateSkillMd(content) {
    if (!content.startsWith('---')) {
      return t('skills.uploadNoFrontmatter');
    }

    var end = content.indexOf('---', 3);
    if (end === -1) {
      return t('skills.uploadNoFrontmatter');
    }

    var frontmatter = content.substring(3, end).trim();
    var lines = frontmatter.split('\n');
    var hasName = false;
    var hasDesc = false;

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (/^name\s*:/.test(line) && line.split(':').slice(1).join(':').trim()) {
        hasName = true;
      }
      if (/^description\s*:/.test(line) && line.split(':').slice(1).join(':').trim()) {
        hasDesc = true;
      }
    }

    if (!hasName) return t('skills.uploadNoName');
    if (!hasDesc) return t('skills.uploadNoDesc');
    return null;
  }

  // ========================================================================
  // Modal helpers
  // ========================================================================

  window.closeModal = function() {
    modalEl.classList.add('hidden');
  };

  modalEl.addEventListener('click', function(e) {
    if (e.target === modalEl) closeModal();
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
  });

  // ========================================================================
  // Utility
  // ========================================================================

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  function t(key) {
    return (typeof i18n !== 'undefined') ? i18n.t(key) : key;
  }

  // -- Init -----------------------------------------------------------------
  loadSkills();
  if (typeof i18n !== 'undefined') i18n.apply();
})();
