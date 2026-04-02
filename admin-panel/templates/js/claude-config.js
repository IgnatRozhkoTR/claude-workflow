// ═══════════════════════════════════════════════
//  CLAUDE COMMAND & CHANNELS CONFIG
// ═══════════════════════════════════════════════

function loadClaudeCommand() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/command')
    .then(function(data) {
      var input = document.getElementById('claudeCommandInput');
      var checkbox = document.getElementById('skipPermissionsCheck');
      if (input) input.value = data.claude_command || 'claude';
      if (checkbox) checkbox.checked = data.skip_permissions !== false;
      if (data.restrict_to_workspace !== undefined) {
        var restrictCheckbox = document.getElementById('restrictToWorkspaceCheck');
        if (restrictCheckbox) restrictCheckbox.checked = data.restrict_to_workspace;
      }
      var pathsInput = document.getElementById('allowedExternalPathsInput');
      if (pathsInput) pathsInput.value = data.allowed_external_paths || '/tmp/';
    })
    .catch(function() {});
}

function saveClaudeCommand() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var input = document.getElementById('claudeCommandInput');
  var checkbox = document.getElementById('skipPermissionsCheck');
  var restrictCheck = document.getElementById('restrictToWorkspaceCheck');
  var pathsInput = document.getElementById('allowedExternalPathsInput');

  var cmd = input ? input.value.trim() : 'claude';
  var skip = checkbox ? checkbox.checked : true;

  apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/command', {
    claude_command: cmd,
    skip_permissions: skip,
    restrict_to_workspace: restrictCheck ? restrictCheck.checked : true,
    allowed_external_paths: pathsInput ? pathsInput.value.trim() : '/tmp/'
  })
  .then(function(data) {
    if (data.ok) {
      var btn = document.querySelector('[onclick="saveClaudeCommand()"]');
      if (btn) {
        var original = btn.textContent;
        btn.textContent = t('actions.copied') || 'Saved!';
        setTimeout(function() { btn.textContent = original; }, 1500);
      }
    }
  })
  .catch(function(e) {
    showToast('Save failed: ' + e.message);
  });
}

function _codexReviewBadgeClass(status) {
  if (status === 'completed') return 'badge badge-success';
  if (status === 'running') return 'badge badge-warning';
  if (status === 'failed') return 'badge badge-danger';
  return 'badge';
}

function _codexReviewStatusLabel(status) {
  if (status === 'completed') return t('status.codexReviewCompleted');
  if (status === 'running') return t('status.codexReviewRunning');
  if (status === 'failed') return t('status.codexReviewFailed');
  return t('status.codexReviewIdle');
}

function updateCodexWorkspaceSettings() {
  var card = document.getElementById('codexSettingsCard');
  if (!card) return;

  var globallyEnabled = !!LOCK_DATA.codex_globally_enabled;
  card.style.display = globallyEnabled ? '' : 'none';
  if (!globallyEnabled) return;

  var checkbox = document.getElementById('codexReviewCheck');
  if (checkbox) checkbox.checked = !!LOCK_DATA.codex_review_enabled;

  var statusRow = document.getElementById('codexReviewStatusRow');
  if (!statusRow) return;

  var status = LOCK_DATA.codex_review_status || 'idle';
  var shouldShowStatus = !!LOCK_DATA.codex_review_enabled || status === 'running' || status === 'failed' || status === 'completed';
  if (!shouldShowStatus) {
    statusRow.style.display = 'none';
    statusRow.innerHTML = '';
    return;
  }

  var errorHtml = '';
  if (status === 'failed' && LOCK_DATA.codex_review_last_error) {
    errorHtml = '<div style="margin-top: 6px;">' + escapeHtml(LOCK_DATA.codex_review_last_error) + '</div>';
  }

  statusRow.style.display = 'block';
  statusRow.innerHTML =
    '<span style="margin-right: 8px;">' + t('config.codexReviewStatus') + '</span>' +
    '<span class="' + _codexReviewBadgeClass(status) + '">' + _codexReviewStatusLabel(status) + '</span>' +
    errorHtml;
}

async function toggleCodexReview(enabled) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var checkbox = document.getElementById('codexReviewCheck');
  var previousEnabled = !!LOCK_DATA.codex_review_enabled;

  if (checkbox) checkbox.disabled = true;
  try {
    var result = await apiPut(
      '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/codex-review',
      { enabled: !!enabled }
    );
    LOCK_DATA.codex_review_enabled = !!result.codex_review_enabled;
    LOCK_DATA.codex_review_status = result.codex_review_status || 'idle';
    LOCK_DATA.codex_review_last_error = result.codex_review_last_error || '';
    updateCodexWorkspaceSettings();
  } catch (e) {
    LOCK_DATA.codex_review_enabled = previousEnabled;
    if (checkbox) checkbox.checked = previousEnabled;
    if (typeof showToast === 'function') showToast('Failed to save: ' + e.message);
  } finally {
    if (checkbox) checkbox.disabled = false;
  }
}

function loadChannelsPreference() {
  var defaultValue = 'plugin:telegram@claude-plugins-official';
  var enabled = localStorage.getItem('channels_enabled') === 'true';
  var value = localStorage.getItem('channels_value') || defaultValue;
  localStorage.setItem('channels_enabled', enabled ? 'true' : 'false');
  localStorage.setItem('channels_value', value);
}

function saveChannelsPreference() {
  // No-op — channels preference is now managed via modules
}

// ═══════════════════════════════════════════════
//  MODULES CARD (dashboard)
// ═══════════════════════════════════════════════

async function loadModulesCard() {
  var card = document.getElementById('modulesCard');
  var body = document.getElementById('modulesCardBody');
  if (!card || !body) return;

  try {
    var modulesData = await apiGet('/api/modules');
    var enabledData = await apiGet('/api/modules/enabled');
    var modules = modulesData.modules || [];
    var enabledIds = enabledData.modules || [];

    if (modules.length === 0) {
      card.style.display = 'none';
      return;
    }

    card.style.display = '';
    var enabledSet = {};
    enabledIds.forEach(function(id) { enabledSet[id] = true; });

    var html = modules.map(function(mod) {
      var checked = enabledSet[mod.id] ? 'checked' : '';
      return '<div style="display: flex; align-items: center; gap: 8px; padding: 4px 0;">'
        + '<input type="checkbox" id="module-' + escapeHtml(mod.id) + '" data-module-id="' + escapeHtml(mod.id) + '" ' + checked + ' onchange="saveModuleToggle()">'
        + '<label for="module-' + escapeHtml(mod.id) + '" style="font-size: 0.82rem; color: var(--text-primary); cursor: pointer;">' + escapeHtml(mod.name) + '</label>'
        + '</div>';
    }).join('');

    body.innerHTML = html;
  } catch (e) {
    console.warn('Failed to load modules card:', e.message);
    card.style.display = 'none';
  }
}

async function saveModuleToggle() {
  var checkboxes = document.querySelectorAll('#modulesCardBody input[type="checkbox"]');
  var enabled = [];
  checkboxes.forEach(function(cb) {
    if (cb.checked) enabled.push(cb.getAttribute('data-module-id'));
  });

  try {
    await apiPost('/api/modules/enabled', { modules: enabled });

    // Update channels preference for backward compatibility
    var telegramEnabled = enabled.indexOf('telegram') !== -1;
    localStorage.setItem('channels_enabled', telegramEnabled ? 'true' : 'false');
    if (telegramEnabled) {
      localStorage.setItem('channels_value', 'plugin:telegram@claude-plugins-official');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('Failed to save: ' + e.message);
  }
}
