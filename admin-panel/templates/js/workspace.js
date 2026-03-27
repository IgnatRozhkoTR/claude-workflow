let _wsCurrentView = 'project-list';
let _wsSelectedProjectId = null;
let _wsSelectedProjectName = null;
let _wsShowArchived = false;

function showProjectSelector() {
  document.getElementById('project-selector').style.display = 'flex';
  document.getElementById('app-content').style.display = 'none';
  _wsSwitchView('project-list');
  loadProjects();
}

function hideProjectSelector() {
  document.getElementById('project-selector').style.display = 'none';
  document.getElementById('app-content').style.display = 'block';
}

function _wsSwitchView(view) {
  _wsCurrentView = view;
  const listView = document.getElementById('ws-project-list-view');
  const workspaceView = document.getElementById('ws-workspace-view');
  if (view === 'project-list') {
    listView.style.display = 'block';
    workspaceView.style.display = 'none';
  } else {
    listView.style.display = 'none';
    workspaceView.style.display = 'block';
  }
}

function _wsRenderCopyCommand(command) {
  const id = 'cmd-' + Math.random().toString(36).substring(2, 9);
  return `<div class="command-block">
    <code id="${id}">${_wsEscape(command)}</code>
    <button class="btn btn-sm" onclick="_wsCopyCommand('${id}', this)">${t('buttons.copy')}</button>
  </div>`;
}

function _wsCopyCommand(codeId, btn) {
  const text = document.getElementById(codeId).textContent;
  navigator.clipboard.writeText(text);
  const original = btn.textContent;
  btn.textContent = t('buttons.copied');
  setTimeout(() => { btn.textContent = original; }, 1500);
}

function _wsEscape(str) {
  const el = document.createElement('span');
  el.textContent = str;
  return el.innerHTML.replace(/'/g, '&#39;');
}

function _wsToggleSessions(id, event) {
  event.stopPropagation();
  const el = document.getElementById(id);
  if (!el) return;
  const isHidden = el.style.display === 'none';
  el.style.display = isHidden ? 'block' : 'none';
}

function _wsClearError(containerId) {
  const container = document.getElementById(containerId);
  if (container) container.textContent = '';
}

function _wsShowError(containerId, message) {
  const container = document.getElementById(containerId);
  if (container) {
    container.textContent = message;
    container.style.color = 'var(--danger)';
    container.style.fontSize = '0.78rem';
    container.style.marginTop = '8px';
  }
}

async function loadProjects() {
  const listEl = document.getElementById('ws-project-cards');
  listEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px;">' + t('workspace.loadingProjects') + '</div>';
  _wsClearError('ws-project-list-error');

  try {
    const data = await apiListProjects();
    const projects = data.projects || [];
    if (projects.length === 0) {
      listEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px; font-style: italic;">' + t('workspace.noProjectsRegistered') + '</div>';
      return;
    }

    listEl.innerHTML = projects.map(p => `
      <div class="ws-project-card">
        <div class="ws-project-card-info">
          <div class="ws-project-card-name">${_wsEscape(p.name)}</div>
          <div class="ws-project-card-path">${_wsEscape(p.path)}</div>
        </div>
        <div class="ws-project-card-actions">
          <button class="btn btn-primary btn-sm" onclick="openProject('${_wsEscape(p.id)}')">${t('buttons.open')}</button>
          <button class="btn btn-danger btn-sm" onclick="_wsRemoveProject('${_wsEscape(p.id)}')">${t('buttons.remove')}</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    _wsShowError('ws-project-list-error', err.message);
  }
}

async function _wsRemoveProject(projectId) {
  _wsClearError('ws-project-list-error');
  try {
    await apiDeleteProject(projectId);
    await loadProjects();
  } catch (err) {
    _wsShowError('ws-project-list-error', err.message);
  }
}

async function _wsRegisterProject() {
  const pathInput = document.getElementById('ws-register-path');
  const nameInput = document.getElementById('ws-register-name');
  const path = pathInput.value.trim();
  const name = nameInput.value.trim() || undefined;

  _wsClearError('ws-register-error');

  if (!path) {
    _wsShowError('ws-register-error', t('errors.directoryPathRequired'));
    return;
  }

  try {
    await apiRegisterProject(name, path);
    pathInput.value = '';
    nameInput.value = '';
    await loadProjects();
  } catch (err) {
    _wsShowError('ws-register-error', err.message);
  }
}

function _wsRenderWorkspaceCards(projectId, workspaces) {
  var active = workspaces.filter(function(ws) { return ws.status !== 'archived'; });
  var archived = workspaces.filter(function(ws) { return ws.status === 'archived'; });
  var visible = _wsShowArchived ? workspaces : active;

  if (visible.length === 0) {
    var msg = workspaces.length > 0
      ? t('workspace.allArchived') + ' <a href="#" onclick="_wsToggleArchived(event)" style="color:var(--accent)">' + t('workspace.showArchived', {count: archived.length}) + '</a>'
      : t('workspace.noWorkspacesYet');
    return '<div style="color: var(--text-muted); padding: 12px; font-style: italic;">' + msg + '</div>';
  }

  var toggleHtml = '';
  if (archived.length > 0) {
    var label = _wsShowArchived ? t('workspace.hideArchived', {count: archived.length}) : t('workspace.showArchived', {count: archived.length});
    toggleHtml = '<div style="margin-bottom:8px;text-align:right;"><a href="#" onclick="_wsToggleArchived(event)" style="font-size:0.78rem;color:var(--text-muted)">' + label + '</a></div>';
  }

  return toggleHtml + visible.map(function(ws) {
    var isArchived = ws.status === 'archived';
    var sessions = ws.sessions || [];

    var actionHtml = isArchived
      ? '<span class="badge" style="background:var(--text-muted);color:var(--bg-base);opacity:0.7">' + t('badges.archived') + '</span>'
      : '<button class="btn btn-danger btn-sm" onclick="_wsArchiveWorkspace(\'' + _wsEscape(projectId) + '\', \'' + _wsEscape(ws.branch) + '\', event)">' + t('buttons.archive') + '</button>';

    var branchLabel = _wsEscape(ws.branch);
    if (isArchived && ws.created) {
      var d = new Date(ws.created);
      var dateStr = d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) +
        ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      branchLabel += ' <span style="color:var(--text-muted);font-weight:400;font-size:0.75rem">(' + dateStr + ')</span>';
    }

    var cardClass = 'ws-workspace-card' + (isArchived ? ' ws-workspace-card--archived' : '');
    var onclick = isArchived ? '' : ' onclick="openWorkspace(\'' + _wsEscape(projectId) + '\', \'' + _wsEscape(ws.branch) + '\')"';

    return '<div class="' + cardClass + '"' + onclick + '>' +
      '<div class="ws-workspace-card-info">' +
        '<div class="ws-workspace-card-branch">' + branchLabel + '</div>' +
        '<div class="ws-workspace-card-meta">' +
          (ws.phase != null ? '<span class="badge badge-warning">' + t('badges.phase', {phase: ws.phase}) + '</span>' : '') +
          (sessions.length > 0 && !isArchived ? '<span class="badge badge-info">' + t('badges.sessionActive') + '</span>' : '') +
          actionHtml +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}

function _wsToggleArchived(event) {
  event.preventDefault();
  _wsShowArchived = !_wsShowArchived;
  if (_wsSelectedProjectId) openProject(_wsSelectedProjectId);
}

async function openProject(projectId) {
  _wsSelectedProjectId = projectId;
  _wsSwitchView('workspace');

  const headerEl = document.getElementById('ws-workspace-project-name');
  headerEl.textContent = t('research.loading');

  const workspaceListEl = document.getElementById('ws-workspace-cards');
  workspaceListEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px;">' + t('workspace.loadingWorkspaces') + '</div>';
  _wsClearError('ws-workspace-error');

  try {
    const data = await apiListProjects();
    const projects = data.projects || [];
    const project = projects.find(p => p.id === projectId);
    _wsSelectedProjectName = project ? project.name : projectId;
    headerEl.textContent = _wsSelectedProjectName;
  } catch (err) {
    headerEl.textContent = projectId;
  }

  try {
    const wsData = await apiListWorkspaces(projectId);
    const workspaces = wsData.workspaces || [];
    workspaceListEl.innerHTML = _wsRenderWorkspaceCards(projectId, workspaces);
  } catch (err) {
    _wsShowError('ws-workspace-error', err.message);
  }

  await loadBranches(projectId);
}

async function loadBranches(projectId) {
  const selectEl = document.getElementById('ws-source-branch');
  selectEl.innerHTML = '<option value="">' + t('workspace.loadingBranches') + '</option>';

  try {
    const brData = await apiListBranches(projectId);
    const branches = [...new Set([...(brData.local || []), ...(brData.remote || [])])];
    if (branches.length === 0) {
      selectEl.innerHTML = '<option value="">' + t('workspace.noBranchesFound') + '</option>';
      return;
    }

    const developExists = branches.includes('develop');
    const defaultBranch = developExists ? 'develop' : branches[0];

    selectEl.innerHTML = branches.map(b =>
      `<option value="${_wsEscape(b)}" ${b === defaultBranch ? 'selected' : ''}>${_wsEscape(b)}</option>`
    ).join('');
  } catch (err) {
    selectEl.innerHTML = '<option value="">' + t('workspace.failedToLoadBranches') + '</option>';
  }
}

async function createWorkspace(projectId) {
  const branchInput = document.getElementById('ws-new-branch');
  const sourceSelect = document.getElementById('ws-source-branch');
  const worktreeCheckbox = document.getElementById('ws-worktree');
  const resultEl = document.getElementById('ws-create-result');

  const branch = branchInput.value.trim();
  const source = sourceSelect.value;
  const worktree = worktreeCheckbox.checked;

  _wsClearError('ws-create-error');
  resultEl.innerHTML = '';

  if (!branch) {
    _wsShowError('ws-create-error', t('errors.branchNameRequired'));
    return;
  }

  try {
    const result = await apiCreateWorkspace(projectId, branch, source, worktree);

    let resultHtml = '<div class="ws-create-result-card">';
    if (result.working_dir) {
      resultHtml += `<div class="ws-result-row">
        <span class="ws-result-label">${t('labels.workingDirectory')}</span>
        <span class="ws-result-value">${_wsEscape(result.working_dir)}</span>
      </div>`;
    }
    resultHtml += `<button class="btn btn-primary" style="margin-top: 12px; width: 100%; justify-content: center;" onclick="openWorkspace('${_wsEscape(projectId)}', '${_wsEscape(branch)}')">${t('buttons.openWorkspace')}</button>`;
    resultHtml += '</div>';

    resultEl.innerHTML = resultHtml;
    branchInput.value = '';

    const workspaceListEl = document.getElementById('ws-workspace-cards');
    const wsData2 = await apiListWorkspaces(projectId);
    const workspaces = wsData2.workspaces || [];
    workspaceListEl.innerHTML = _wsRenderWorkspaceCards(projectId, workspaces);
  } catch (err) {
    _wsShowError('ws-create-error', err.message);
  }
}

async function _wsArchiveWorkspace(projectId, branch, event) {
  event.stopPropagation();
  if (!confirm(t('dialog.archiveWorkspace', {branch: branch}))) return;
  _wsClearError('ws-workspace-error');
  try {
    await apiArchiveWorkspace(projectId, branch);
    await openProject(projectId);
  } catch (err) {
    _wsShowError('ws-workspace-error', err.message);
  }
}

function openWorkspace(projectId, branch) {
  setWorkspaceContext(projectId, branch);
  hideProjectSelector();
  if (typeof initApp === 'function') {
    initApp();
  }
}

function _wsInitSelector() {
  const selector = document.getElementById('project-selector');
  if (!selector) return;

  selector.innerHTML = `
    <div class="ws-selector-container">
      <div class="ws-selector-header">
        <h1 class="ws-selector-title">${t('workspace.workspaceControl')}</h1>
        <p class="ws-selector-subtitle">${t('workspace.selectProject')}</p>
      </div>

      <div id="ws-project-list-view">
        <div class="ws-section">
          <div class="ws-section-title">${t('workspace.registeredProjects')}</div>
          <div id="ws-project-cards"></div>
          <div id="ws-project-list-error"></div>
        </div>

        <div class="ws-section">
          <div class="ws-section-title">${t('workspace.registerNewProject')}</div>
          <div class="ws-register-form">
            <input type="text" id="ws-register-path" class="ws-input"
              placeholder="${t('placeholders.projectPath')}">
            <input type="text" id="ws-register-name" class="ws-input"
              placeholder="${t('placeholders.projectName')}">
            <button class="btn btn-primary" onclick="_wsRegisterProject()">${t('buttons.register')}</button>
          </div>
          <div id="ws-register-error"></div>
        </div>

        <div class="ws-section" style="border-top: 1px solid var(--border); padding-top: 16px;">
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-sm btn-outline" onclick="showSetupPage()" style="flex: 1; justify-content: center;">
              ${t('setup.openSetupBtn')}
            </button>
            <button class="btn btn-sm btn-outline" onclick="showImprovementsPage()" style="flex: 1; justify-content: center;">
              ${t('improvements.openBtn')}
            </button>
          </div>
        </div>
      </div>

      <div id="ws-workspace-view" style="display: none;">
        <button class="ws-back-btn" onclick="_wsBackToProjects()">
          <span class="ws-back-arrow">&larr;</span> ${t('buttons.backToProjects')}
        </button>

        <div class="ws-section">
          <div class="ws-section-title" id="ws-workspace-project-name"></div>
          <div id="ws-workspace-cards"></div>
          <div id="ws-workspace-error"></div>
        </div>

        <div class="ws-section">
          <div class="ws-section-title">${t('workspace.createNewWorkspace')}</div>
          <div class="ws-create-form">
            <input type="text" id="ws-new-branch" class="ws-input"
              placeholder="${t('placeholders.featureBranch')}" required>
            <div class="ws-form-row">
              <label class="ws-label">${t('labels.sourceBranch')}</label>
              <select id="ws-source-branch" class="ws-select">
                <option value="">${t('research.loading')}</option>
              </select>
            </div>
            <div class="ws-form-row">
              <label class="ws-checkbox-label">
                <input type="checkbox" id="ws-worktree" checked>
                ${t('labels.createAsGitWorktree')}
              </label>
            </div>
            <button class="btn btn-primary" onclick="createWorkspace(_wsSelectedProjectId)">${t('buttons.createWorkspace')}</button>
          </div>
          <div id="ws-create-error"></div>
          <div id="ws-create-result"></div>
        </div>
      </div>
    </div>
  `;

  if (!document.getElementById('selector-toolbar')) {
    var toolbar = document.createElement('div');
    toolbar.id = 'selector-toolbar';
    toolbar.style.cssText = 'position: absolute; top: 16px; right: 24px; display: flex; gap: 8px; align-items: center; z-index: 10;';
    toolbar.innerHTML = '<select class="locale-select" id="selectorLocaleSelect" onchange="onSelectorLocaleChange(this.value)"><option value="en">EN</option><option value="ru">RU</option></select>'
      + '<button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme" id="selectorThemeBtn">&#9788;</button>';
    selector.appendChild(toolbar);
  }

  var localeSelect = document.getElementById('selectorLocaleSelect');
  if (localeSelect && typeof I18N_LOCALE !== 'undefined') {
    localeSelect.value = I18N_LOCALE;
  }
  if (typeof _updateThemeButtons === 'function' && typeof state !== 'undefined') {
    _updateThemeButtons(state.theme);
  }
}

function onSelectorLocaleChange(value) {
  localStorage.setItem('admin-panel-locale', value);
  I18N_LOCALE = value;
  loadI18n(value).then(function() {
    _wsInitSelector();
    loadProjects();
    var workspaceLocaleSelect = document.getElementById('localeSelect');
    if (workspaceLocaleSelect) workspaceLocaleSelect.value = value;
  });
}

function _wsBackToProjects() {
  _wsSelectedProjectId = null;
  _wsSelectedProjectName = null;
  _wsSwitchView('project-list');
  loadProjects();
}

(function () {
  const ctx = getWorkspaceContext();
  const savedLocale = localStorage.getItem('admin-panel-locale');
  const needsLocaleLoad = savedLocale && savedLocale !== 'en' && typeof loadI18n === 'function';

  function _wsBoot() {
    _wsInitSelector();
    if (ctx) {
      hideProjectSelector();
      if (typeof initApp === 'function') {
        initApp();
      }
    } else {
      showProjectSelector();
      loadProjects();
    }
  }

  if (needsLocaleLoad) {
    loadI18n(savedLocale).then(_wsBoot);
  } else {
    _wsBoot();
  }
})();
