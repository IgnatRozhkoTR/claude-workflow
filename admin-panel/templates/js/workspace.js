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
  return el.innerHTML;
}

function _wsRelativeDate(isoString) {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffMin < 1) return t('time.justNow');
  if (diffMin < 60) return t('time.minAgo', {n: diffMin});
  if (diffHour < 24) return diffHour === 1 ? t('time.hourAgo', {n: diffHour}) : t('time.hoursAgo', {n: diffHour});
  if (diffDay < 7) return diffDay === 1 ? t('time.dayAgo', {n: diffDay}) : t('time.daysAgo', {n: diffDay});
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
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

  _wsInjectStyles();
}

function _wsBackToProjects() {
  _wsSelectedProjectId = null;
  _wsSelectedProjectName = null;
  _wsSwitchView('project-list');
  loadProjects();
}

function _wsInjectStyles() {
  if (document.getElementById('ws-styles')) return;

  const style = document.createElement('style');
  style.id = 'ws-styles';
  style.textContent = `
    #project-selector {
      position: fixed;
      inset: 0;
      z-index: 9999;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--bg-base);
      overflow-y: auto;
    }

    #project-selector::before {
      content: '';
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        radial-gradient(ellipse 60% 50% at 20% 0%, var(--accent-dim) 0%, transparent 70%),
        radial-gradient(ellipse 40% 60% at 85% 100%, var(--info-dim) 0%, transparent 70%);
    }

    .ws-selector-container {
      position: relative;
      width: 100%;
      max-width: 640px;
      padding: 40px 24px;
    }

    .ws-selector-header {
      text-align: center;
      margin-bottom: 36px;
    }

    .ws-selector-title {
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 6px;
    }

    .ws-selector-subtitle {
      font-size: 0.88rem;
      color: var(--text-muted);
    }

    .ws-section {
      margin-bottom: 28px;
    }

    .ws-section-title {
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }

    .ws-project-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      margin-bottom: 8px;
      transition: border-color var(--transition);
    }

    .ws-project-card:hover {
      border-color: color-mix(in srgb, var(--border-active) 40%, var(--border));
    }

    .ws-project-card-info {
      flex: 1;
      min-width: 0;
    }

    .ws-project-card-name {
      font-weight: 600;
      font-size: 0.88rem;
      margin-bottom: 2px;
    }

    .ws-project-card-path {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .ws-project-card-actions {
      display: flex;
      gap: 6px;
      margin-left: 12px;
      flex-shrink: 0;
    }

    .ws-register-form,
    .ws-create-form {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .ws-input {
      width: 100%;
      padding: 10px 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--bg-input);
      color: var(--text-primary);
      font-family: var(--font-mono);
      font-size: 0.82rem;
      transition: border-color var(--transition);
    }

    .ws-input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-dim);
    }

    .ws-input::placeholder {
      color: var(--text-muted);
      font-family: var(--font-sans);
    }

    .ws-select {
      width: 100%;
      padding: 10px 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--bg-input);
      color: var(--text-primary);
      font-family: var(--font-mono);
      font-size: 0.82rem;
      cursor: pointer;
      transition: border-color var(--transition);
      appearance: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23888' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 12px center;
      padding-right: 36px;
    }

    .ws-select:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-dim);
    }

    .ws-select option {
      background: var(--bg-raised);
      color: var(--text-primary);
    }

    .ws-form-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .ws-label {
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--text-secondary);
    }

    .ws-checkbox-label {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.82rem;
      color: var(--text-secondary);
      cursor: pointer;
    }

    .ws-checkbox-label input[type="checkbox"] {
      accent-color: var(--accent);
    }

    .ws-back-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      margin-bottom: 16px;
      background: none;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      color: var(--text-secondary);
      font-family: var(--font-sans);
      font-size: 0.82rem;
      cursor: pointer;
      transition: var(--transition);
    }

    .ws-back-btn:hover {
      border-color: var(--border-active);
      color: var(--text-primary);
    }

    .ws-back-arrow {
      font-size: 1rem;
      line-height: 1;
    }

    .ws-workspace-card {
      padding: 14px 18px;
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      margin-bottom: 8px;
      cursor: pointer;
      transition: border-color var(--transition);
    }

    .ws-workspace-card:hover {
      border-color: var(--border-active);
    }

    .ws-workspace-card--archived {
      opacity: 0.55;
      cursor: default;
    }

    .ws-workspace-card--archived:hover {
      border-color: var(--border);
    }

    .ws-workspace-card-info {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .ws-workspace-card-branch {
      font-family: var(--font-mono);
      font-size: 0.85rem;
      font-weight: 600;
    }

    .ws-workspace-card-meta {
      display: flex;
      gap: 6px;
      flex-shrink: 0;
    }

    .command-block {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      padding: 8px 12px;
      background: var(--bg-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
    }

    .command-block code {
      flex: 1;
      font-family: var(--font-mono);
      font-size: 0.78rem;
      color: var(--text-secondary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .command-block .btn {
      flex-shrink: 0;
    }

    .ws-sessions-toggle {
      margin-top: 6px;
    }

    .ws-sessions-link {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-decoration: none;
    }

    .ws-sessions-link:hover {
      color: var(--accent);
    }

    .ws-sessions-dropdown {
      margin-top: 6px;
      padding: 8px 10px;
      background: var(--bg-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
    }

    .ws-session-history-item {
      padding: 6px 0;
      border-bottom: 1px solid var(--border);
    }

    .ws-session-history-item:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }

    .ws-session-history-item:first-child {
      padding-top: 0;
    }

    .ws-session-history-date {
      font-size: 0.72rem;
      color: var(--text-muted);
    }

    .ws-create-result-card {
      margin-top: 12px;
      padding: 16px;
      background: var(--success-dim);
      border: 1px solid color-mix(in srgb, var(--success) 30%, transparent);
      border-radius: var(--radius);
    }

    .ws-result-row {
      margin-bottom: 8px;
    }

    .ws-result-label {
      display: block;
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 4px;
    }

    .ws-result-value {
      font-family: var(--font-mono);
      font-size: 0.82rem;
      color: var(--text-primary);
      word-break: break-all;
    }
  `;
  document.head.appendChild(style);
}

(function () {
  const ctx = getWorkspaceContext();
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
})();
