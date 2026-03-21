// ═══════════════════════════════════════════════
//  GIT CONFIG & RULES
// ═══════════════════════════════════════════════

function toggleGitLabFields() {
  var provider = document.getElementById('gitProvider').value;
  var fields = document.getElementById('gitLabFields');
  if (fields) {
    fields.style.display = provider === 'gitlab' ? '' : 'none';
  }
}

function loadGitConfig() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiGet('/api/projects/' + encodeURIComponent(ctx.projectId) + '/git-config')
    .then(function(config) {
      var provider = document.getElementById('gitProvider');
      var host = document.getElementById('gitHost');
      var token = document.getElementById('gitToken');
      var branch = document.getElementById('gitDefaultBranch');
      if (provider) provider.value = config.provider || 'local';
      if (host) host.value = config.host || '';
      if (token) token.value = config.token || '';
      if (branch) branch.value = config.default_branch || 'develop';
      toggleGitLabFields();
    }).catch(function() {});
}

function saveGitConfig() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var config = {
    provider: document.getElementById('gitProvider').value,
    host: document.getElementById('gitHost').value,
    token: document.getElementById('gitToken').value,
    default_branch: document.getElementById('gitDefaultBranch').value || 'develop'
  };

  apiPut('/api/projects/' + encodeURIComponent(ctx.projectId) + '/git-config', config)
    .then(function() { showToast(t('messages.gitConfigSaved')); })
    .catch(function(e) { showToast(t('messages.gitSaveFailed', {error: e.message})); });
}

function loadGitRules() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiGet('/api/projects/' + encodeURIComponent(ctx.projectId) + '/git-rules')
    .then(function(data) {
      var textarea = document.getElementById('gitRulesContent');
      var source = document.getElementById('gitRulesSource');
      if (textarea) textarea.value = data.content || '';
      if (source) {
        var labels = { 'system-default': t('gitRules.sourceSystemDefault'), 'project': t('gitRules.sourceProject'), 'not-configured': t('gitRules.sourceNotConfigured') };
        source.textContent = t('gitRules.source', {label: labels[data.source] || data.source});
      }
    }).catch(function() {});
}

function saveGitRules() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var content = document.getElementById('gitRulesContent').value;

  apiPut('/api/projects/' + encodeURIComponent(ctx.projectId) + '/git-rules', { content: content })
    .then(function(data) {
      showToast(t('messages.gitRulesSaved'));
      var source = document.getElementById('gitRulesSource');
      if (source) source.textContent = t('gitRules.source', {label: t('gitRules.sourceProject')});
    })
    .catch(function(e) { showToast(t('messages.gitSaveFailed', {error: e.message})); });
}
