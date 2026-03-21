// ═══════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════

async function initApp() {
  const ctx = getWorkspaceContext();

  if (!ctx) {
    showProjectSelector();
    return;
  }

  try {
    const stateData = await apiGetState(ctx.projectId, ctx.branch);

    LOCK_DATA.branch = ctx.branch;
    LOCK_DATA.session_id = stateData.session_id || null;
    LOCK_DATA.working_dir = stateData.working_dir || null;
    LOCK_DATA.sessions = stateData.sessions || [];

    applyStateData(stateData);

    if (LOCK_DATA.locale && LOCK_DATA.locale !== 'en') {
      await loadI18n(LOCK_DATA.locale);
    }
  } catch (e) {
    console.warn('API unavailable, using static data:', e.message);
  }

  try {
    const contextData = await apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context');
    if (contextData) {
      CONTEXT_DATA = contextData;
    }
  } catch (e) {
    console.warn('Context API unavailable:', e.message);
  }

  try {
    const diffData = await apiGetDiff(ctx.projectId, ctx.branch, state.diffSource);
    if (diffData && diffData.files) {
      DIFF_DATA = diffData;
    }
  } catch (e) {
    console.warn('Diff API unavailable, using static data:', e.message);
  }

  document.getElementById('branchName').textContent = LOCK_DATA.branch || ctx.branch;
  document.getElementById('phaseLabel').textContent = t('phase.label', {phase: state.phase, name: getPhaseName(state.phase)});

  // Update browser tab title with branch name
  if (LOCK_DATA.branch) {
    document.title = LOCK_DATA.branch + ' — Workspace Control';
  } else {
    document.title = 'Workspace Control';
  }

  var localeSelect = document.getElementById('localeSelect');
  if (localeSelect && LOCK_DATA.locale) {
    localeSelect.value = LOCK_DATA.locale;
  }

  var yoloCheck = document.getElementById('yoloCheck');
  if (yoloCheck) yoloCheck.checked = !!LOCK_DATA.yolo_mode;

  if (LOCK_DATA.session_id) {
    var sessionBlock = document.getElementById('sessionBlock');
    if (sessionBlock) {
      sessionBlock.style.display = '';
    }
  }

  loadReviewComments();

  renderPhaseBar('phaseBarControl', 'phaseLabelsControl');
  renderPhaseHistory();
  renderPlan();
  renderScope();
  updateScopeStatusUI(LOCK_DATA.scope_status || 'pending');
  updatePlanApprovalUI(LOCK_DATA.plan_status || 'pending');
  renderResearch();
  renderPreplanning();
  renderFileList();
  renderPhaseActions();
  renderApprovalStatus();
  renderContext();
  loadCriteria();
  loadGitConfig();
  loadGitRules();
  loadClaudeCommand();
  loadChannelsPreference();

  // Restore diff toggle states from localStorage
  document.querySelectorAll('#viewModeToggle .toggle-opt').forEach(function(b) {
    b.classList.toggle('active', b.dataset.mode === state.fileView);
  });
  document.querySelectorAll('#diffModeToggle .toggle-opt').forEach(function(b) {
    b.classList.toggle('active', b.dataset.mode === state.diffMode);
  });
  document.querySelectorAll('#diffSourceToggle .toggle-opt').forEach(function(b) {
    b.classList.toggle('active', b.dataset.mode === state.diffSource);
  });

  hideProjectSelector();
  setupCollapsibleCards();
  _initialLoad = false;
}

// ═══════════════════════════════════════════════
//  CLIPBOARD HELPERS
// ═══════════════════════════════════════════════

function safeCopyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(function() {
      return fallbackCopy(text);
    });
  }
  return fallbackCopy(text);
}

function fallbackCopy(text) {
  return new Promise(function(resolve) {
    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    try { document.execCommand('copy'); } catch(e) {}
    document.body.removeChild(textarea);
    resolve();
  });
}

// ═══════════════════════════════════════════════
//  TERMINAL COMMANDS
// ═══════════════════════════════════════════════

function showTerminalDropdown(type, btn) {
  document.querySelectorAll('.btn-dropdown-menu').forEach(function(m) { m.style.display = 'none'; });

  var dropdown = document.getElementById(type + 'Dropdown');
  if (dropdown) {
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
  }

  setTimeout(function() {
    document.addEventListener('click', function closeDropdown(e) {
      if (!e.target.closest('.btn-dropdown')) {
        document.querySelectorAll('.btn-dropdown-menu').forEach(function(m) { m.style.display = 'none'; });
        document.removeEventListener('click', closeDropdown);
      }
    });
  }, 10);
}

function doTerminalAction(endpoint, btnId, mode) {
  document.querySelectorAll('.btn-dropdown-menu').forEach(function(m) { m.style.display = 'none'; });

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var btn = document.getElementById(btnId);
  if (btn) btn.disabled = true;

  var channelsEnabled = localStorage.getItem('channels_enabled') === 'true';
  var channelsValue = localStorage.getItem('channels_value') || '';
  var body = {};
  if (channelsEnabled && channelsValue) {
    body.channels = channelsValue;
  }

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/terminal/' + endpoint, body)
    .then(function(result) {
      if (mode === 'split') {
        var container = document.getElementById('splitContainer');
        if (container && !container.classList.contains('split-active')) {
          toggleSplitTerminal();
        } else if (container && container.classList.contains('split-active')) {
          connectSplitTerminal();
        }
      } else {
        switchTab('terminal');
        setTimeout(function() { connectTerminal(); }, 500);
      }

      if (typeof loadTerminalSessions === 'function') loadTerminalSessions();

      safeCopyToClipboard(result.attach_command).then(function() {
        if (btn) {
          var original = btn.textContent;
          btn.textContent = t('actions.copied');
          btn.disabled = false;
          setTimeout(function() { btn.textContent = original; }, 1500);
        }
      });
    })
    .catch(function(e) {
      if (btn) btn.disabled = false;
      showToast(endpoint.charAt(0).toUpperCase() + endpoint.slice(1) + ' failed: ' + e.message);
    });
}

function doStart(mode) {
  doTerminalAction('start', 'startBtn', mode);
}

function doResume(mode) {
  doTerminalAction('resume', 'resumeBtn', mode);
}

function doNotify(type) {
  document.querySelectorAll('.btn-dropdown-menu').forEach(function(m) { m.style.display = 'none'; });

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var messages = {
    'comments': 'I left review comments for you to address. Check workspace_get_comments for details.',
    'go': 'You can proceed. Continue with the current task.'
  };

  var message = messages[type] || messages['go'];

  var btn = document.getElementById('notifyBtn');
  if (btn) btn.disabled = true;

  fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/terminal/notify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: message })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (btn) {
      var original = btn.textContent;
      btn.textContent = t('actions.notified');
      btn.disabled = false;
      setTimeout(function() { btn.textContent = original; }, 1500);
    }
  })
  .catch(function(e) {
    if (btn) btn.disabled = false;
    showToast('Notify failed: ' + e.message);
  });
}

function copyWorkspacePath() {
  var workingDir = LOCK_DATA.working_dir;
  if (!workingDir) return;
  var cmd = 'cd ' + workingDir;
  safeCopyToClipboard(cmd).then(function() {
    var btn = document.getElementById('copyPathBtn');
    if (!btn) return;
    btn.textContent = t('actions.copied');
    setTimeout(function() { btn.textContent = t('actions.copyPath'); }, 1500);
  });
}

function onLocaleChange(locale) {
  setLocale(locale);
}

function toggleYoloMode(enabled) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  LOCK_DATA.yolo_mode = enabled;
  apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/yolo',
    { enabled: enabled });
}

function setupCollapsibleCards() {
  document.querySelectorAll('.card-header').forEach(function(header) {
    if (header.querySelector('.card-collapse-chevron')) return;

    var chevron = document.createElement('span');
    chevron.className = 'card-collapse-chevron';
    chevron.textContent = '\u25BC';
    header.insertBefore(chevron, header.firstChild);

    header.addEventListener('click', function(e) {
      if (e.target.closest('button, input, select, textarea, .diagram-zoom-controls, .comment-icon, .comment-icon-header, .comment-thread, a')) return;
      this.closest('.card').classList.toggle('collapsed');
    });

    if (!header.closest('.card').classList.contains('card-primary')) {
      header.closest('.card').classList.add('collapsed');
    }
  });
}

