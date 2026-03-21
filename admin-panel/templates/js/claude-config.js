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

function loadChannelsPreference() {
  var defaultValue = 'plugin:telegram@claude-plugins-official';
  var enabled = localStorage.getItem('channels_enabled') === 'true';
  var value = localStorage.getItem('channels_value') || defaultValue;
  var check = document.getElementById('channelsEnabledCheck');
  var input = document.getElementById('channelsValueInput');
  if (check) check.checked = enabled;
  if (input) {
    input.value = value;
    input.style.display = enabled ? '' : 'none';
  }
}

function saveChannelsPreference() {
  var defaultValue = 'plugin:telegram@claude-plugins-official';
  var check = document.getElementById('channelsEnabledCheck');
  var input = document.getElementById('channelsValueInput');
  if (!check || !input) return;
  if (!input.value) input.value = defaultValue;
  localStorage.setItem('channels_enabled', check.checked ? 'true' : 'false');
  localStorage.setItem('channels_value', input.value);
  input.style.display = check.checked ? '' : 'none';
}
