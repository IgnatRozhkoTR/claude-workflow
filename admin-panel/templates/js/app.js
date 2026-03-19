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

  var localeSelect = document.getElementById('localeSelect');
  if (localeSelect && LOCK_DATA.locale) {
    localeSelect.value = LOCK_DATA.locale;
  }

  if (LOCK_DATA.session_id) {
    var sessionBlock = document.getElementById('sessionBlock');
    if (sessionBlock) {
      sessionBlock.style.display = '';
    }
  }

  if (LOCK_DATA.sessions.length > 1) {
    var sessionsHistoryBlock = document.getElementById('sessionsHistoryBlock');
    if (sessionsHistoryBlock) {
      sessionsHistoryBlock.style.display = '';
      var btn = document.getElementById('sessionsHistoryBtn');
      if (btn) {
        btn.textContent = t('workspace.sessions', {count: LOCK_DATA.sessions.length});
      }
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

function copyStartCommand() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var btn = document.getElementById('startBtn');
  if (btn) btn.disabled = true;

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/terminal/start', {})
    .then(function(result) {
      navigator.clipboard.writeText(result.attach_command).then(function() {
        if (btn) {
          var original = btn.textContent;
          btn.textContent = t('actions.copied');
          btn.disabled = false;
          setTimeout(function() { btn.textContent = original; }, 1500);
        }
      });

      switchTab('terminal');
      setTimeout(function() { connectTerminal(); }, 500);
    })
    .catch(function(e) {
      if (btn) btn.disabled = false;
      showToast('Start failed: ' + e.message);
    });
}

function copyResumeCommand() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var btn = document.getElementById('resumeBtn');
  if (btn) btn.disabled = true;

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/terminal/resume', {})
    .then(function(result) {
      navigator.clipboard.writeText(result.attach_command).then(function() {
        if (btn) {
          var original = btn.textContent;
          btn.textContent = t('actions.copied');
          btn.disabled = false;
          setTimeout(function() { btn.textContent = original; }, 1500);
        }
      });

      switchTab('terminal');
      setTimeout(function() { connectTerminal(); }, 500);
    })
    .catch(function(e) {
      if (btn) btn.disabled = false;
      showToast('Resume failed: ' + e.message);
    });
}

function copyWorkspacePath() {
  var workingDir = LOCK_DATA.working_dir;
  if (!workingDir) return;
  var cmd = 'cd ' + workingDir;
  navigator.clipboard.writeText(cmd).then(function() {
    var btn = document.getElementById('copyPathBtn');
    if (!btn) return;
    btn.textContent = t('actions.copied');
    setTimeout(function() { btn.textContent = t('actions.copyPath'); }, 1500);
  });
}

function toggleSessionsHistory() {
  var dropdown = document.getElementById('sessionsHistoryDropdown');
  if (!dropdown) return;
  var isHidden = dropdown.style.display === 'none';
  if (!isHidden) {
    dropdown.style.display = 'none';
    return;
  }
  var workingDir = LOCK_DATA.working_dir;
  var html = LOCK_DATA.sessions.map(function(s) {
    var cmd = (workingDir ? 'cd ' + workingDir + ' && ' : '') + 'claude --dangerously-skip-permissions -r ' + s.session_id;
    var escapedCmd = cmd.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    var cmdId = 'scmd-' + Math.random().toString(36).substring(2, 9);
    return '<div style="padding: 6px 0; border-bottom: 1px solid var(--border);">' +
      '<div style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 4px;">' + formatRelativeDate(s.started_at) + '</div>' +
      '<div style="display: flex; align-items: center; gap: 8px;">' +
        '<code id="' + cmdId + '" style="flex: 1; font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">' + escapedCmd + '</code>' +
        '<button class="btn btn-sm" onclick="_sessionCopyCmd(\'' + cmdId + '\', this)" style="flex-shrink: 0;">' + t('buttons.copy') + '</button>' +
      '</div>' +
    '</div>';
  }).join('');
  dropdown.innerHTML = html;
  dropdown.style.display = 'block';
}

function _sessionCopyCmd(codeId, btn) {
  var text = document.getElementById(codeId).textContent;
  navigator.clipboard.writeText(text).then(function() {
    var original = btn.textContent;
    btn.textContent = t('buttons.copied');
    setTimeout(function() { btn.textContent = original; }, 1500);
  });
}

function onLocaleChange(locale) {
  setLocale(locale);
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

