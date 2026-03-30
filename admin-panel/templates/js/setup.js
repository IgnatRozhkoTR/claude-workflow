// ═══════════════════════════════════════════════
//  SETUP PAGE
// ═══════════════════════════════════════════════

var _navigatingBack = false;

var _setupTerm = null;
var _setupFitAddon = null;
var _setupTermWs = null;
var _setupTermConnected = false;
var _setupCustomProfiles = [];
var _setupCachedProfiles = [];

// ─── Navigation ───

function showSetupPage() {
  var listView = document.getElementById('ws-project-list-view');
  var workspaceView = document.getElementById('ws-workspace-view');
  var setupView = document.getElementById('ws-setup-view');
  var improvementsView = document.getElementById('ws-improvements-view');
  if (listView) listView.style.display = 'none';
  if (workspaceView) workspaceView.style.display = 'none';
  if (improvementsView) improvementsView.style.display = 'none';
  if (setupView) {
    setupView.style.display = 'block';
  } else {
    _setupInjectView();
  }
  if (!_navigatingBack) {
    history.pushState({ view: 'setup' }, '', '?view=setup');
  }
  loadSetupData();
}

function hideSetupPage() {
  var setupView = document.getElementById('ws-setup-view');
  var listView = document.getElementById('ws-project-list-view');
  if (setupView) setupView.style.display = 'none';
  if (listView) listView.style.display = 'block';
  disconnectSetupTerminal();
  if (!_navigatingBack) {
    history.pushState({ view: 'projects' }, '', '/');
  }
}

// ─── View injection ───

function _setupInjectView() {
  var container = document.querySelector('.ws-selector-container');
  if (!container) return;

  var setupView = document.createElement('div');
  setupView.id = 'ws-setup-view';
  setupView.innerHTML = renderSetupPage();
  container.appendChild(setupView);
}

// ─── Data loading ───

async function loadSetupData() {
  var setupView = document.getElementById('ws-setup-view');
  if (!setupView) return;

  setupView.innerHTML = renderSetupPage();

  var modulesEl = document.getElementById('setup-modules');
  var languagesEl = document.getElementById('setup-languages');

  if (modulesEl) {
    modulesEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px 18px;">' + t('research.loading') + '</div>';
  }
  if (languagesEl) {
    languagesEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px 18px;">' + t('research.loading') + '</div>';
  }

  var modules = [];
  var enabledModules = [];
  var profiles = [];

  try {
    var modulesData = await apiGet('/api/modules');
    modules = modulesData.modules || [];
  } catch (e) {
    console.warn('Failed to load modules:', e.message);
  }

  try {
    var enabledData = await apiGet('/api/modules/enabled');
    enabledModules = enabledData.modules || [];
  } catch (e) {
    console.warn('Failed to load enabled modules:', e.message);
  }

  try {
    var profilesData = await apiGet('/api/verification/profiles');
    profiles = profilesData.profiles || [];
  } catch (e) {
    console.warn('Failed to load verification profiles:', e.message);
  }

  _setupCachedProfiles = profiles;
  if (modulesEl) modulesEl.innerHTML = renderSetupModules(modules, enabledModules);
  if (languagesEl) languagesEl.innerHTML = renderSetupLanguages(profiles);
}

// ─── Rendering ───

function renderSetupPage() {
  return '<div class="setup-container">'
    + '<button class="ws-back-btn" onclick="hideSetupPage()">'
    + '<span class="ws-back-arrow">&larr;</span> ' + t('setup.backToProjects')
    + '</button>'
    + '<h2 style="margin: 16px 0 4px;">' + t('setup.title') + '</h2>'
    + '<p style="color: var(--text-muted); margin: 0 0 20px; font-size: 0.875rem;">' + t('setup.subtitle') + '</p>'

    + '<div class="setup-section">'
    + '<div class="setup-section-title">' + t('setup.modulesTitle') + '</div>'
    + '<div id="setup-modules"><div style="color: var(--text-muted); padding: 12px 18px;">' + t('research.loading') + '</div></div>'
    + '</div>'

    + '<div class="setup-section">'
    + '<div class="setup-section-title">' + t('setup.profilesTitle') + '</div>'
    + '<div id="setup-languages"><div style="color: var(--text-muted); padding: 12px 18px;">' + t('research.loading') + '</div></div>'

    + '<div class="setup-custom-form">'
    + '<div class="setup-section-title" style="margin-top: 16px;">' + t('setup.customProfileTitle') + '</div>'
    + '<input id="setup-custom-name" class="ws-input" style="margin-bottom: 8px;" placeholder="' + t('setup.customProfileNamePlaceholder') + '">'
    + '<input id="setup-custom-config" class="ws-input" style="margin-bottom: 8px;" placeholder="' + t('setup.customConfigPlaceholder') + '">'
    + '<textarea id="setup-custom-details" class="ws-input" style="margin-bottom: 8px; min-height: 60px; resize: vertical;" placeholder="' + t('setup.customDetailsPlaceholder') + '"></textarea>'
    + '<div style="color: var(--text-muted); font-size: 0.78rem; margin-bottom: 4px;">' + t('setup.lspServerLabel') + '</div>'
    + '<input id="setup-custom-lsp-command" class="ws-input" style="margin-bottom: 8px;" placeholder="' + t('setup.lspCommandPlaceholder') + '">'
    + '<input id="setup-custom-lsp-install-command" class="ws-input" style="margin-bottom: 8px;" placeholder="' + t('setup.lspInstallCommandPlaceholder') + '">'
    + '<button class="btn btn-sm" style="margin-top: 8px;" onclick="addCustomProfile()">' + t('setup.addProfileBtn') + '</button>'
    + '</div>'
    + '</div>'

    + '<div class="setup-section">'
    + '<div class="setup-section-title">LSP Keyboard Shortcuts</div>'
    + '<div id="setup-shortcuts">'
    + (typeof renderSetupShortcutsSection === 'function' ? renderSetupShortcutsSection() : '')
    + '</div>'
    + '</div>'

    + '<div id="setup-error" style="color: var(--danger); font-size: 0.78rem; margin-top: 8px;"></div>'
    + '<button class="btn btn-primary setup-start-btn" style="margin-top: 20px; width: 100%; justify-content: center;" onclick="startSetup()">'
    + t('setup.startBtn')
    + '</button>'

    + '<div class="setup-terminal-section" id="setup-terminal-section" style="display: none;">'
    + '<div class="setup-terminal-header">'
    + '<span id="setup-terminal-status" class="terminal-status">' + t('terminal.disconnected') + '</span>'
    + '<button class="btn btn-sm btn-outline" onclick="disconnectSetupTerminal()" id="setup-terminal-disconnect-btn" style="display: none;">'
    + t('setup.terminalDisconnectBtn')
    + '</button>'
    + '</div>'
    + '<div id="setup-terminal-container"></div>'
    + '</div>'

    + '</div>';
}

function renderSetupModules(modules, enabledModules) {
  if (modules.length === 0) {
    return '<div style="color: var(--text-muted); padding: 12px 18px; font-style: italic;">' + t('setup.noModules') + '</div>';
  }

  var enabledSet = {};
  enabledModules.forEach(function(id) { enabledSet[id] = true; });

  return modules.map(function(mod) {
    var id = mod.id || mod.name || mod;
    var label = mod.label || mod.name || mod;
    var description = mod.description || '';
    var isChecked = enabledSet[id] ? 'checked' : '';

    var descHtml = description
      ? '<div style="color: var(--text-muted); font-size: 0.78rem; margin-top: 2px;">' + _wsEscape(description) + '</div>'
      : '';

    return '<label class="ws-checkbox-label" style="display: flex; align-items: flex-start; gap: 8px; padding: 10px 18px; cursor: pointer;">'
      + '<input type="checkbox" class="setup-module-checkbox" data-module-id="' + _wsEscape(id) + '" ' + isChecked + ' style="margin-top: 2px;">'
      + '<div>'
      + '<div>' + _wsEscape(label) + '</div>'
      + descHtml
      + '</div>'
      + '</label>';
  }).join('');
}

function renderSetupLanguages(profiles) {
  var defaultsHtml = '';

  if (profiles.length === 0 && _setupCustomProfiles.length === 0) {
    defaultsHtml = '<div style="color: var(--text-muted); padding: 12px 18px; font-style: italic;">' + t('setup.noLanguageProfiles') + '</div>';
  } else {
    defaultsHtml = profiles.map(function(profile) {
      var id = profile.id;
      var name = _wsEscape(profile.name || '');
      var language = _wsEscape(profile.language || '');
      var lspCommand = profile.lsp_command ? _wsEscape(profile.lsp_command) : '';

      var lspBadge = lspCommand
        ? '<span class="badge" style="font-size: 0.65rem; padding: 1px 6px; background: var(--info, #0d6efd); color: #fff; border-radius: 3px; margin-left: 4px;">LSP: ' + lspCommand + '</span>'
        : '';

      return '<div style="display: flex; align-items: center; gap: 8px; padding: 10px 18px;">'
        + '<label class="ws-checkbox-label" style="display: flex; align-items: center; gap: 8px; cursor: pointer; flex: 1;">'
        + '<input type="checkbox" class="setup-language-checkbox" data-profile-id="' + id + '">'
        + '<span>' + name + '</span>'
        + (language ? '<span style="color: var(--text-muted); font-size: 0.78rem;">(' + language + ')</span>' : '')
        + lspBadge
        + '</label>'
        + '<button class="btn btn-sm btn-outline" style="font-size: 0.72rem; color: var(--danger, #dc3545); border-color: var(--danger, #dc3545);" onclick="deleteVerificationProfile(' + id + ')">&times;</button>'
        + '</div>';
    }).join('');
  }

  var customHtml = _setupCustomProfiles.map(function(cp, index) {
    var lspBadge = cp.lsp_command
      ? '<span class="badge" style="font-size: 0.65rem; padding: 1px 6px; background: var(--info, #0d6efd); color: #fff; border-radius: 3px; margin-left: 4px;">LSP: ' + _wsEscape(cp.lsp_command) + '</span>'
      : '';
    return '<div style="display: flex; align-items: center; gap: 8px; padding: 10px 18px; border-top: 1px solid var(--border);">'
      + '<span style="font-size: 0.82rem;">' + _wsEscape(cp.name) + '</span>'
      + (cp.config ? '<span style="color: var(--text-muted); font-size: 0.78rem;">(' + _wsEscape(cp.config) + ')</span>' : '')
      + '<span class="badge" style="font-size: 0.65rem; padding: 1px 6px; background: var(--accent); color: var(--accent-text); border-radius: 3px; margin-left: 4px;">custom</span>'
      + lspBadge
      + '<button class="btn btn-sm btn-outline" style="margin-left: auto; font-size: 0.72rem;" onclick="removeCustomProfile(' + index + ')">' + t('setup.removeToolBtn') + '</button>'
      + '</div>';
  }).join('');

  return defaultsHtml + customHtml;
}

// ─── Custom profile form ───

function _reRenderLanguages() {
  var languagesEl = document.getElementById('setup-languages');
  if (!languagesEl) return;

  var checkedProfileIds = [];
  document.querySelectorAll('.setup-language-checkbox:checked').forEach(function(cb) {
    checkedProfileIds.push(cb.getAttribute('data-profile-id'));
  });

  languagesEl.innerHTML = renderSetupLanguages(_setupCachedProfiles);

  checkedProfileIds.forEach(function(id) {
    var cb = document.querySelector('.setup-language-checkbox[data-profile-id="' + id + '"]');
    if (cb) cb.checked = true;
  });
}

function addCustomProfile() {
  var nameEl = document.getElementById('setup-custom-name');
  var configEl = document.getElementById('setup-custom-config');
  var detailsEl = document.getElementById('setup-custom-details');
  var lspCommandEl = document.getElementById('setup-custom-lsp-command');
  var lspInstallCommandEl = document.getElementById('setup-custom-lsp-install-command');

  var name = nameEl ? nameEl.value.trim() : '';
  var config = configEl ? configEl.value.trim() : '';
  var details = detailsEl ? detailsEl.value.trim() : '';
  var lspCommand = lspCommandEl ? lspCommandEl.value.trim() : '';
  var lspInstallCommand = lspInstallCommandEl ? lspInstallCommandEl.value.trim() : '';

  if (!name) {
    if (nameEl) nameEl.focus();
    return;
  }

  _setupCustomProfiles.push({ name: name, config: config, details: details, lsp_command: lspCommand, lsp_install_command: lspInstallCommand });

  if (nameEl) nameEl.value = '';
  if (configEl) configEl.value = '';
  if (detailsEl) detailsEl.value = '';
  if (lspCommandEl) lspCommandEl.value = '';
  if (lspInstallCommandEl) lspInstallCommandEl.value = '';

  _reRenderLanguages();
}

function removeCustomProfile(index) {
  _setupCustomProfiles.splice(index, 1);
  _reRenderLanguages();
}

async function deleteVerificationProfile(profileId) {
  if (!confirm('Delete this profile and all its steps? This cannot be undone.')) return;
  try {
    var resp = await fetch('/api/verification/profiles/' + profileId, { method: 'DELETE' });
    var data = await resp.json();
    if (!resp.ok) {
      if (typeof showToast === 'function') showToast('Delete failed: ' + (data.error || 'unknown error'));
      return;
    }
    _setupCachedProfiles = _setupCachedProfiles.filter(function(p) { return p.id !== profileId; });
    _reRenderLanguages();
  } catch (e) {
    if (typeof showToast === 'function') showToast('Delete failed: ' + e.message);
  }
}

// ─── Config collection ───

function getSetupConfig() {
  var selectedModules = [];
  document.querySelectorAll('.setup-module-checkbox:checked').forEach(function(cb) {
    selectedModules.push(cb.getAttribute('data-module-id'));
  });

  var selectedProfileIds = [];
  document.querySelectorAll('.setup-language-checkbox:checked').forEach(function(cb) {
    selectedProfileIds.push(parseInt(cb.getAttribute('data-profile-id')));
  });

  var customLanguages = _setupCustomProfiles.map(function(cp) {
    var entry = { name: cp.name, config: cp.config, details: cp.details };
    if (cp.lsp_command) entry.lsp_command = cp.lsp_command;
    if (cp.lsp_install_command) entry.lsp_install_command = cp.lsp_install_command;
    return entry;
  });

  return {
    modules: selectedModules,
    languages: selectedProfileIds,
    custom_languages: customLanguages
  };
}

// ─── Setup execution ───

async function startSetup() {
  var errorEl = document.getElementById('setup-error');
  if (errorEl) errorEl.textContent = '';

  var config = getSetupConfig();

  if (typeof collectSetupShortcuts === 'function' && typeof saveLspShortcuts === 'function') {
    saveLspShortcuts(collectSetupShortcuts());
  }

  try {
    await apiPost('/api/modules/enabled', { modules: config.modules });
  } catch (e) {
    if (errorEl) {
      errorEl.textContent = t('setup.saveModulesFailed') + ': ' + e.message;
    }
    return;
  }

  var termSection = document.getElementById('setup-terminal-section');
  if (termSection) termSection.style.display = 'block';

  var startBtn = document.querySelector('.setup-start-btn');
  if (startBtn) startBtn.disabled = true;

  try {
    var result = await apiPost('/api/setup/start', config);
    var sessionName = result.session || 'setup';
    connectSetupTerminal(sessionName);
  } catch (e) {
    if (errorEl) {
      errorEl.textContent = t('setup.startFailed') + ': ' + e.message;
    }
    if (startBtn) startBtn.disabled = false;
  }
}

// ─── Terminal integration ───

function connectSetupTerminal(sessionName) {
  if (!_setupTerm) {
    var result = _createTerminal('setup-terminal-container', function() { return _setupTermWs; });
    if (!result) return;
    _setupTerm = result.terminal;
    _setupFitAddon = result.fitAddon;
  }

  if (_setupTermWs && _setupTermWs.readyState === WebSocket.OPEN) return;

  var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = protocol + '//' + window.location.host + '/ws/setup-terminal';

  _setupUpdateTerminalStatus('connecting');

  _setupTermWs = _connectTerminal(_setupTerm, _setupFitAddon, wsUrl, {
    focusOnOpen: true,
    onConnected: function() {
      _setupTermConnected = true;
      _setupUpdateTerminalStatus('connected');
    },
    onDisconnected: function() {
      _setupTermConnected = false;
      _setupUpdateTerminalStatus('disconnected');
      if (_setupTerm) _setupTerm.writeln('\r\n\x1b[33m' + t('setup.terminalDisconnected') + '\x1b[0m');
    },
    onError: function() {
      _setupTermConnected = false;
      _setupUpdateTerminalStatus('error');
      if (_setupTerm) _setupTerm.writeln('\r\n\x1b[31m' + t('setup.terminalError') + '\x1b[0m');
    }
  });
}

function disconnectSetupTerminal() {
  if (_setupTermWs) {
    _setupTermWs.close();
    _setupTermWs = null;
  }
  _setupTermConnected = false;
  _setupUpdateTerminalStatus('disconnected');
}

function _setupUpdateTerminalStatus(status) {
  var el = document.getElementById('setup-terminal-status');
  var disconnectBtn = document.getElementById('setup-terminal-disconnect-btn');

  if (el) {
    switch (status) {
      case 'connected':
        el.textContent = t('terminal.connected');
        el.className = 'terminal-status connected';
        break;
      case 'connecting':
        el.textContent = t('terminal.connecting');
        el.className = 'terminal-status';
        break;
      case 'error':
        el.textContent = t('terminal.error');
        el.className = 'terminal-status';
        break;
      default:
        el.textContent = t('terminal.disconnected');
        el.className = 'terminal-status';
    }
  }

  if (disconnectBtn) {
    disconnectBtn.style.display = (status === 'connected') ? '' : 'none';
  }
}

// ═══════════════════════════════════════════════
//  IMPROVEMENTS PAGE (global, no workspace required)
// ═══════════════════════════════════════════════

// ─── Navigation ───

function showImprovementsPage() {
  var listView = document.getElementById('ws-project-list-view');
  var workspaceView = document.getElementById('ws-workspace-view');
  var setupView = document.getElementById('ws-setup-view');
  var improvementsView = document.getElementById('ws-improvements-view');
  if (listView) listView.style.display = 'none';
  if (workspaceView) workspaceView.style.display = 'none';
  if (setupView) setupView.style.display = 'none';
  if (improvementsView) {
    improvementsView.style.display = 'block';
  } else {
    _improvementsInjectView();
  }
  if (!_navigatingBack) {
    history.pushState({ view: 'improvements' }, '', '?view=improvements');
  }
  loadGlobalImprovements();
}

function hideImprovementsPage() {
  var improvementsView = document.getElementById('ws-improvements-view');
  var listView = document.getElementById('ws-project-list-view');
  if (improvementsView) improvementsView.style.display = 'none';
  if (listView) listView.style.display = 'block';
  if (!_navigatingBack) {
    history.pushState({ view: 'projects' }, '', '/');
  }
}

// ─── View injection ───

function _improvementsInjectView() {
  var container = document.querySelector('.ws-selector-container');
  if (!container) return;
  var view = document.createElement('div');
  view.id = 'ws-improvements-view';
  view.innerHTML = _renderImprovementsPage();
  container.appendChild(view);
}

function _renderImprovementsPage() {
  return '<div class="setup-container">'
    + '<button class="ws-back-btn" onclick="hideImprovementsPage()">'
    + '<span class="ws-back-arrow">&larr;</span> ' + t('setup.backToProjects')
    + '</button>'
    + '<h2 style="margin: 16px 0 4px;">' + t('improvements.globalTitle') + '</h2>'
    + '<p style="color: var(--text-muted); margin: 0 0 20px; font-size: 0.875rem;">' + t('improvements.globalSubtitle') + '</p>'

    + '<div style="display: flex; gap: 8px; margin-bottom: 16px;">'
    + '<select id="globalImprovementScopeFilter" class="ws-select" onchange="loadGlobalImprovements()">'
    + '<option value="">' + t('improvements.allScopes') + '</option>'
    + '<option value="workflow">workflow</option>'
    + '<option value="project">project</option>'
    + '<option value="tooling">tooling</option>'
    + '<option value="process">process</option>'
    + '</select>'
    + '<select id="globalImprovementStatusFilter" class="ws-select" onchange="loadGlobalImprovements()">'
    + '<option value="">' + t('improvements.allStatuses') + '</option>'
    + '<option value="open">' + t('improvements.open') + '</option>'
    + '<option value="resolved">' + t('improvements.resolved') + '</option>'
    + '</select>'
    + '</div>'

    + '<div id="globalImprovementsList"></div>'
    + '</div>';
}

// ─── Data loading ───

async function loadGlobalImprovements() {
  var container = document.getElementById('globalImprovementsList');
  if (!container) return;
  container.innerHTML = '<div style="color: var(--text-muted); padding: 12px;">' + t('research.loading') + '</div>';

  var scopeFilter = document.getElementById('globalImprovementScopeFilter');
  var statusFilter = document.getElementById('globalImprovementStatusFilter');
  var params = new URLSearchParams();
  if (scopeFilter && scopeFilter.value) params.set('scope', scopeFilter.value);
  if (statusFilter && statusFilter.value) params.set('status', statusFilter.value);

  try {
    var data = await apiGet('/api/improvements' + (params.toString() ? '?' + params.toString() : ''));
    renderGlobalImprovements(data.improvements || []);
  } catch (e) {
    container.innerHTML = '<div class="no-items-msg">' + t('improvements.noItems') + '</div>';
  }
}

// ─── Rendering ───

function renderGlobalImprovements(items) {
  var container = document.getElementById('globalImprovementsList');
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = '<div class="no-items-msg">' + t('improvements.noItems') + '</div>';
    return;
  }

  container.innerHTML = items.map(function(item) {
    return renderImprovementItem(item, {
      escapeFn: _wsEscape,
      onResolve: 'resolveGlobalImprovement',
      onReopen: 'reopenGlobalImprovement'
    });
  }).join('');
}

// ─── Actions ───

async function resolveGlobalImprovement(id) {
  var note = prompt(t('improvements.resolvePrompt'));
  if (note === null) return;
  try {
    await apiPut('/api/improvements/' + id + '/resolve', {note: note});
    await loadGlobalImprovements();
  } catch (e) {
    if (typeof showToast === 'function') showToast('Failed to resolve: ' + e.message);
  }
}

async function reopenGlobalImprovement(id) {
  try {
    await apiPut('/api/improvements/' + id + '/reopen');
    await loadGlobalImprovements();
  } catch (e) {
    if (typeof showToast === 'function') showToast('Failed to reopen: ' + e.message);
  }
}

// ─── Browser history navigation ───

window.addEventListener('popstate', function(event) {
  _navigatingBack = true;
  var state = event.state;
  if (state && state.view === 'setup') {
    showSetupPage();
  } else if (state && state.view === 'improvements') {
    showImprovementsPage();
  } else {
    var setupView = document.getElementById('ws-setup-view');
    var improvementsView = document.getElementById('ws-improvements-view');
    var listView = document.getElementById('ws-project-list-view');
    if (setupView) setupView.style.display = 'none';
    if (improvementsView) improvementsView.style.display = 'none';
    if (listView) listView.style.display = 'block';
  }
  _navigatingBack = false;
});
