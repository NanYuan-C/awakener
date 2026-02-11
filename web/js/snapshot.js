/**
 * Awakener - Snapshot Page Logic
 * ==============================
 * Fetches and renders the system snapshot (asset inventory).
 */

(function() {
  'use strict';

  // -- DOM References -------------------------------------------------------
  const els = {
    content: document.getElementById('snapshot-content'),
    loading: document.getElementById('snapshot-loading'),
    empty: document.getElementById('snapshot-empty'),
    metaUpdated: document.getElementById('meta-updated'),
    metaRound: document.getElementById('meta-round'),
    servicesTable: document.getElementById('services-table').querySelector('tbody'),
    servicesEmpty: document.getElementById('services-empty'),
    projectsList: document.getElementById('projects-list'),
    projectsEmpty: document.getElementById('projects-empty'),
    toolsList: document.getElementById('tools-list'),
    toolsEmpty: document.getElementById('tools-empty'),
    docsList: document.getElementById('documents-list'),
    docsEmpty: document.getElementById('documents-empty'),
    envGrid: document.getElementById('env-grid'),
    issuesList: document.getElementById('issues-list'),
    issuesEmpty: document.getElementById('issues-empty'),
  };

  // -- Renderers ------------------------------------------------------------

  function renderServices(services) {
    els.servicesTable.innerHTML = '';
    if (!services || services.length === 0) {
      els.servicesEmpty.classList.remove('hidden');
      document.getElementById('services-table').classList.add('hidden');
      return;
    }
    document.getElementById('services-table').classList.remove('hidden');
    els.servicesEmpty.classList.add('hidden');

    services.forEach(s => {
      const tr = document.createElement('tr');
      
      // Health badge
      let healthClass = 'badge-gray';
      if (s.health === 'healthy') healthClass = 'badge-green';
      else if (s.health === 'degraded') healthClass = 'badge-yellow';
      else if (s.health === 'down') healthClass = 'badge-red';

      // Status icon
      let statusIcon = '&#x25CF;'; // circle
      let statusColor = '#ccc';
      if (s.status === 'running') statusColor = '#28a745';
      else if (s.status === 'error') statusColor = '#dc3545';

      tr.innerHTML = `
        <td>
          <div class="font-bold">${escapeHtml(s.name)}</div>
          ${s.domain ? `<div class="text-xs text-muted">${escapeHtml(s.domain)}</div>` : ''}
        </td>
        <td>${s.port || '-'}</td>
        <td><span style="color:${statusColor}; margin-right:4px;">${statusIcon}</span> ${escapeHtml(s.status)}</td>
        <td>
          <span class="badge ${healthClass}">${escapeHtml(s.health)}</span>
          ${s.health_note ? `<div class="text-xs text-muted mt-xs">${escapeHtml(s.health_note)}</div>` : ''}
        </td>
        <td class="text-sm font-mono">${escapeHtml(s.path)}</td>
      `;
      els.servicesTable.appendChild(tr);
    });
  }

  function renderProjects(projects) {
    els.projectsList.innerHTML = '';
    if (!projects || projects.length === 0) {
      els.projectsEmpty.classList.remove('hidden');
      return;
    }
    els.projectsEmpty.classList.add('hidden');

    projects.forEach(p => {
      const div = document.createElement('div');
      div.className = 'p-sm border rounded';
      div.innerHTML = `
        <div class="flex justify-between items-center mb-xs">
          <div class="font-bold">${escapeHtml(p.name)}</div>
          <div class="badge badge-blue text-xs">${escapeHtml(p.stack)}</div>
        </div>
        <div class="text-xs text-muted mb-xs font-mono">${escapeHtml(p.path)}</div>
        <div class="text-sm">${escapeHtml(p.description)}</div>
        ${p.entry ? `<div class="text-xs text-muted mt-xs">Entry: ${escapeHtml(p.entry)}</div>` : ''}
      `;
      els.projectsList.appendChild(div);
    });
  }

  function renderTools(tools) {
    els.toolsList.innerHTML = '';
    if (!tools || tools.length === 0) {
      els.toolsEmpty.classList.remove('hidden');
      return;
    }
    els.toolsEmpty.classList.add('hidden');

    tools.forEach(t => {
      const div = document.createElement('div');
      div.className = 'list-item p-sm border-bottom';
      div.innerHTML = `
        <div class="font-mono text-sm font-bold">${escapeHtml(t.path)}</div>
        <div class="text-sm text-muted">${escapeHtml(t.usage)}</div>
      `;
      els.toolsList.appendChild(div);
    });
  }

  function renderDocuments(docs) {
    els.docsList.innerHTML = '';
    if (!docs || docs.length === 0) {
      els.docsEmpty.classList.remove('hidden');
      return;
    }
    els.docsEmpty.classList.add('hidden');

    docs.forEach(d => {
      const div = document.createElement('div');
      div.className = 'list-item p-sm border-bottom';
      div.innerHTML = `
        <div class="font-mono text-sm font-bold">${escapeHtml(d.path)}</div>
        <div class="text-sm text-muted">${escapeHtml(d.purpose)}</div>
      `;
      els.docsList.appendChild(div);
    });
  }

  function renderEnvironment(env) {
    els.envGrid.innerHTML = '';
    if (!env) return;

    const addRow = (key, value) => {
      if (!value) return;
      const div = document.createElement('div');
      div.className = 'env-row flex justify-between py-xs border-bottom';
      div.innerHTML = `
        <span class="text-muted">${key}</span>
        <span class="font-mono text-sm text-right">${escapeHtml(String(value))}</span>
      `;
      els.envGrid.appendChild(div);
    };

    addRow('OS', env.os);
    addRow('Python', env.python);
    addRow('Domain', env.domain);
    addRow('SSL', env.ssl ? 'Yes' : 'No');
    addRow('Disk Usage', env.disk_usage);
    
    if (env.key_packages && env.key_packages.length > 0) {
      const div = document.createElement('div');
      div.className = 'env-row py-xs';
      div.innerHTML = `
        <div class="text-muted mb-xs">Key Packages</div>
        <div class="flex gap-xs flex-wrap">
          ${env.key_packages.map(p => `<span class="badge badge-gray text-xs">${escapeHtml(p)}</span>`).join('')}
        </div>
      `;
      els.envGrid.appendChild(div);
    }
  }

  function renderIssues(issues) {
    els.issuesList.innerHTML = '';
    if (!issues || issues.length === 0) {
      els.issuesEmpty.classList.remove('hidden');
      return;
    }
    
    const openIssues = issues.filter(i => i.status === 'open');
    if (openIssues.length === 0) {
      els.issuesEmpty.classList.remove('hidden');
      return;
    }
    els.issuesEmpty.classList.add('hidden');

    openIssues.forEach(i => {
      const div = document.createElement('div');
      div.className = 'issue-card p-sm border rounded mb-sm border-left-thick';
      
      // Severity color
      let colorClass = 'border-gray';
      let icon = 'ℹ';
      if (i.severity === 'critical') { colorClass = 'border-red'; icon = '🔴'; }
      else if (i.severity === 'high') { colorClass = 'border-orange'; icon = '🟠'; }
      else if (i.severity === 'medium') { colorClass = 'border-yellow'; icon = '⚠'; }

      div.classList.add(colorClass); // You'd need CSS for these border colors

      div.innerHTML = `
        <div class="flex justify-between">
          <div class="font-bold">${icon} ${escapeHtml(i.summary)}</div>
          <div class="text-xs text-muted">R${i.discovered}</div>
        </div>
        ${i.detail ? `<div class="text-sm mt-xs">${escapeHtml(i.detail)}</div>` : ''}
      `;
      els.issuesList.appendChild(div);
    });
  }

  // -- Main Logic -----------------------------------------------------------

  async function loadSnapshot() {
    try {
      const data = await api.get('/api/snapshot');
      
      els.loading.classList.add('hidden');
      
      if (!data || Object.keys(data).length === 0) {
        els.empty.classList.remove('hidden');
        return;
      }

      els.content.classList.remove('hidden');

      // Meta
      if (data.meta) {
        els.metaUpdated.textContent = data.meta.last_updated || '-';
        els.metaRound.textContent = data.meta.round || '-';
      }

      // Sections
      renderServices(data.services);
      renderProjects(data.projects);
      renderTools(data.tools);
      renderDocuments(data.documents);
      renderEnvironment(data.environment);
      renderIssues(data.issues);

    } catch (e) {
      els.loading.classList.add('hidden');
      toast('Failed to load snapshot: ' + e.message, 'error');
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // -- Init -----------------------------------------------------------------
  loadSnapshot();

})();
