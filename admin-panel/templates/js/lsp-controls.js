// ===============================================
//  LSP CONTROLS (header indicator + profile cards)
// ===============================================

var _lspProfiles = [];
var _lspProjectPath = '';
var _lspPollingInterval = null;

// --- Data loading ---

function loadLspProfiles() {
  var ctx = getWorkspaceContext();
  if (!ctx) return Promise.resolve();

  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/profiles';
  return apiGet(url).then(function(data) {
    _lspProfiles = (data && data.profiles) || [];
    _lspProjectPath = (data && data.project_path) || '';
    if (typeof updateLspLanguageMap === 'function') updateLspLanguageMap();
    renderLspHeaderIndicator();
    renderLspProfileCards();

    var dropdown = document.getElementById('lspDropdown');
    if (dropdown && dropdown.style.display === 'block') {
      renderLspDropdown();
    }

    var hasRunning = _lspProfiles.some(function(p) {
      return p.instance_status === 'running';
    });
    if (hasRunning && !isLspConnected()) {
      connectLsp();
    }
  }).catch(function(e) {
    console.warn('Failed to load LSP profiles:', e.message);
    _lspProfiles = [];
    _lspProjectPath = '';
    if (typeof updateLspLanguageMap === 'function') updateLspLanguageMap();
    renderLspHeaderIndicator();
  });
}

// --- Header indicator ---

function renderLspHeaderIndicator() {
  var indicator = document.getElementById('lspIndicator');
  if (!indicator) return;

  if (_lspProfiles.length === 0) {
    indicator.style.display = 'none';
    return;
  }

  indicator.style.display = '';

  var running = 0;
  var errors = 0;
  var total = _lspProfiles.length;

  _lspProfiles.forEach(function(p) {
    if (p.instance_status === 'running') running++;
    if (p.instance_status === 'error') errors++;
  });

  indicator.className = 'btn btn-sm';

  if (errors > 0) {
    indicator.classList.add('lsp-status-error');
  } else if (running === 0) {
    indicator.classList.add('lsp-status-off');
  } else if (running === total) {
    indicator.classList.add('lsp-status-running');
  } else {
    indicator.classList.add('lsp-status-partial');
  }

  indicator.textContent = 'LSP ' + running + '/' + total;
  indicator.title = 'Language Servers: ' + running + '/' + total + ' running';
}

// --- Dropdown ---

function toggleLspDropdown() {
  var dropdown = document.getElementById('lspDropdown');
  if (!dropdown) return;

  if (dropdown.style.display === 'none' || !dropdown.style.display) {
    renderLspDropdown();
    dropdown.style.display = 'block';

    setTimeout(function() {
      document.addEventListener('click', _closeLspDropdownOnOutsideClick);
    }, 10);
  } else {
    dropdown.style.display = 'none';
    document.removeEventListener('click', _closeLspDropdownOnOutsideClick);
  }
}

function _closeLspDropdownOnOutsideClick(e) {
  if (!e.target.closest('.lsp-control')) {
    var dropdown = document.getElementById('lspDropdown');
    if (dropdown) dropdown.style.display = 'none';
    document.removeEventListener('click', _closeLspDropdownOnOutsideClick);
  }
}

function renderLspDropdown() {
  var dropdown = document.getElementById('lspDropdown');
  if (!dropdown) return;

  var html = '<div class="lsp-dropdown-header">Language Servers</div>';

  if (_lspProfiles.length === 0) {
    html += '<div style="padding: 8px; font-size: 12px; color: var(--text-muted);">No LSP profiles configured</div>';
    dropdown.innerHTML = html;
    return;
  }

  var hasErrors = false;

  _lspProfiles.forEach(function(p) {
    var status = p.instance_status || 'stopped';
    var isRunning = status === 'running';
    var isError = status === 'error';
    if (isError) hasErrors = true;

    var btnHtml = isRunning
      ? '<button class="lsp-btn stop" onclick="stopLspServer(' + p.profile_id + '); event.stopPropagation();">Stop</button>'
      : '<button class="lsp-btn start" onclick="startLspServer(' + p.profile_id + '); event.stopPropagation();">Start</button>';

    html += '<div class="lsp-dropdown-item">'
      + '<div>'
      + '<span class="lsp-server-name">' + escapeHtml(p.name) + '</span>'
      + ' <span class="lsp-server-lang">' + escapeHtml(p.language) + '</span>'
      + '</div>'
      + '<span class="lsp-server-status ' + status + '">' + status + '</span>'
      + btnHtml
      + '</div>';

    if (isError && p.error_message) {
      html += '<div class="lsp-dropdown-error">' + escapeHtml(p.error_message) + '</div>';
    }
  });

  html += '<div class="lsp-dropdown-actions">'
    + '<button class="lsp-btn start" onclick="startAllLsp(); event.stopPropagation();">Start All</button>'
    + '<button class="lsp-btn stop" onclick="stopAllLsp(); event.stopPropagation();">Stop All</button>'
    + '</div>';

  dropdown.innerHTML = html;
}

// --- LSP sections in verification profile cards ---

function renderLspProfileCards() {
  if (_lspProfiles.length === 0) return;

  var lspByAssignmentId = {};
  _lspProfiles.forEach(function(p) {
    lspByAssignmentId[p.assignment_id] = p;
  });

  var cards = document.querySelectorAll('.verification-profile-card');
  cards.forEach(function(card) {
    var removeBtn = card.querySelector('.verification-profile-header button');
    if (!removeBtn) return;

    var onclickAttr = removeBtn.getAttribute('onclick') || '';
    var match = onclickAttr.match(/unassignVerificationProfile\((\d+)\)/);
    if (!match) return;

    var assignmentId = parseInt(match[1]);
    var lspProfile = lspByAssignmentId[assignmentId] || null;

    var existing = card.querySelector('.lsp-profile-section');
    if (existing) existing.remove();

    if (!lspProfile) return;

    var section = document.createElement('div');
    section.className = 'lsp-profile-section';

    var status = lspProfile.instance_status || 'stopped';
    var isRunning = status === 'running';

    var btnHtml = isRunning
      ? '<button class="lsp-btn stop" onclick="stopLspServer(' + lspProfile.profile_id + ')">Stop</button>'
      : '<button class="lsp-btn start" onclick="startLspServer(' + lspProfile.profile_id + ')">Start</button>';

    var toggleChecked = lspProfile.lsp_enabled ? ' checked' : '';

    section.innerHTML = '<div class="lsp-info">'
      + '<div class="lsp-info-left">'
      + '<span class="lsp-server-status ' + status + '">' + status + '</span>'
      + btnHtml
      + '</div>'
      + '<label class="lsp-toggle-label">'
      + '<input type="checkbox"' + toggleChecked + ' onchange="toggleLspProfile(' + lspProfile.profile_id + ', this.checked)">'
      + ' LSP enabled'
      + '</label>'
      + '</div>'
      + '<div class="lsp-command">' + escapeHtml(lspProfile.lsp_command + (lspProfile.lsp_args ? ' ' + lspProfile.lsp_args : '')) + '</div>';

    card.appendChild(section);
  });
}

// --- Server lifecycle ---

function startLspServer(profileId) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/start';
  apiPost(url, { profile_id: profileId }).then(function() {
    return loadLspProfiles();
  }).catch(function(e) {
    if (typeof showToast === 'function') showToast('LSP start failed: ' + e.message);
  });
}

function stopLspServer(profileId) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/stop';
  apiPost(url, { profile_id: profileId }).then(function() {
    loadLspProfiles();
  }).catch(function(e) {
    if (typeof showToast === 'function') showToast('LSP stop failed: ' + e.message);
  });
}

function startAllLsp() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/start';
  apiPost(url, {}).then(function() {
    return loadLspProfiles();
  }).catch(function(e) {
    if (typeof showToast === 'function') showToast('LSP start all failed: ' + e.message);
  });
}

function stopAllLsp() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/stop';
  apiPost(url, {}).then(function() {
    loadLspProfiles();
    disconnectLsp();
  }).catch(function(e) {
    if (typeof showToast === 'function') showToast('LSP stop all failed: ' + e.message);
  });
}

function toggleLspProfile(profileId, enabled) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/profiles/' + profileId + '/toggle';
  apiPut(url, { enabled: enabled }).then(function() {
    loadLspProfiles();
  }).catch(function(e) {
    if (typeof showToast === 'function') showToast('LSP toggle failed: ' + e.message);
    loadLspProfiles();
  });
}

// --- Polling ---

function startLspPolling() {
  stopLspPolling();

  _lspPollingInterval = setInterval(function() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;

    var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/lsp/status';
    apiGet(url).then(function(statuses) {
      if (!Array.isArray(statuses)) return;

      var statusMap = {};
      statuses.forEach(function(s) {
        statusMap[s.profile_id] = s;
      });

      _lspProfiles.forEach(function(p) {
        var updated = statusMap[p.profile_id];
        if (updated) {
          p.instance_status = updated.status;
          p.error_message = updated.error_message;
          p.pid = updated.pid;
        }
      });

      renderLspHeaderIndicator();
    }).catch(function() {
      // Silently ignore polling errors
    });
  }, 10000);
}

function stopLspPolling() {
  if (_lspPollingInterval) {
    clearInterval(_lspPollingInterval);
    _lspPollingInterval = null;
  }
}
