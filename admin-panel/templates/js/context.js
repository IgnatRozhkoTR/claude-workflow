// ═══════════════════════════════════════════════
//  CONTEXT TAB
// ═══════════════════════════════════════════════
let CONTEXT_DATA = {
  ticket_id: '',
  ticket_name: '',
  context: '',
  discussions: [],
  refs: []
};

function renderContext() {
  var idInput = document.getElementById('contextTicketId');
  var nameInput = document.getElementById('contextTicketName');
  var textArea = document.getElementById('contextText');

  if (idInput) idInput.value = CONTEXT_DATA.ticket_id || LOCK_DATA.branch || '';
  if (nameInput) nameInput.value = CONTEXT_DATA.ticket_name || '';
  if (textArea) textArea.value = CONTEXT_DATA.context || '';

  renderDiscussions();
  renderContextRefs();
  renderContextRaw();
}

function renderDiscussions() {
  var container = document.getElementById('discussionsList');
  if (!container) return;
  container.innerHTML = '';

  var discussions = CONTEXT_DATA.discussions || [];
  var badge = document.getElementById('qaBadge');
  var showHidden = container.dataset.showHidden === 'true';

  var visible = discussions.filter(function(d) { return showHidden || !d.hidden; });
  var hiddenCount = discussions.filter(function(d) { return d.hidden; }).length;

  if (badge) {
    var open = discussions.filter(function(d) { return d.status === 'open'; }).length;
    var researchOpen = discussions.filter(function(d) { return d.type === 'research' && d.status === 'open'; }).length;
    badge.textContent = researchOpen > 0 ? t('badges.researchCount', {count: researchOpen}) : (open > 0 ? t('badges.openCount', {count: open}) : t('badges.totalCount', {count: discussions.length}));
    badge.className = 'badge ' + (researchOpen > 0 ? 'badge-danger' : (open > 0 ? 'badge-warning' : 'badge-success'));
  }

  if (visible.length === 0 && hiddenCount === 0) {
    container.innerHTML = '<div class="no-items-msg">' + t('discussions.noItems') + '</div>';
    return;
  }

  visible.forEach(function(d) {
    var div = document.createElement('div');
    div.className = 'qa-item' + (d.status === 'resolved' ? ' qa-answered' : '');

    var author = d.author || 'user';
    var authorBadge = '<span class="qa-author qa-author-' + author + '">' + author + '</span>';
    var typeBadge = d.type === 'research'
      ? '<span class="badge" style="font-size:0.6rem;background:var(--warning-dim);color:var(--warning);margin-left:4px;">' + t('badges.research') + '</span>'
      : '';
    var statusBadge = d.status === 'resolved'
      ? '<span class="badge badge-success" style="font-size:0.65rem">' + t('badges.resolved') + '</span>'
      : '<button class="btn btn-sm" style="font-size:0.65rem;padding:1px 6px" onclick="resolveDiscussion(' + d.id + ')">' + t('buttons.resolve') + '</button>';

    // Link to research findings if any exist
    var researchLink = '';
    if (d.type === 'research' && typeof RESEARCH_DATA !== 'undefined') {
      var linked = RESEARCH_DATA.filter(function(r) { return r.discussion_id === d.id; });
      if (linked.length > 0) {
        researchLink = '<button class="btn btn-sm" style="font-size:0.6rem;padding:1px 6px;margin-left:4px;" onclick="goToResearch(' + d.id + ')" title="' + t('research.viewLinked') + '">' + t('research.findingCount', {count: linked.length}) + '</button>';
      }
    }

    var hideBtn = '<button class="qa-delete" onclick="hideDiscussion(' + d.id + ', ' + (d.hidden ? 'false' : 'true') + ')" title="' + (d.hidden ? t('buttons.unhide') : t('buttons.hide')) + '">' + (d.hidden ? '\u{1F441}' : '\u{1F648}') + '</button>';

    var repliesHtml = '';
    if (d.replies && d.replies.length > 0) {
      repliesHtml = '<div style="margin-top: 6px; padding-left: 16px; border-left: 2px solid var(--border);">';
      d.replies.forEach(function(reply) {
        var replyAuthorBadge = reply.author === 'agent' ? '<span class="badge badge-accent" style="font-size: 10px;">' + t('author.agent') + '</span>' : '<span class="badge" style="font-size: 10px;">' + t('author.user') + '</span>';
        repliesHtml += '<div style="padding: 4px 0; font-size: 13px;">' + replyAuthorBadge + ' ' + escapeHtml(reply.text) + '</div>';
      });
      repliesHtml += '</div>';
    }

    var replyForm = d.status !== 'resolved'
      ? '<div style="margin-top: 6px; display: flex; gap: 4px;">' +
        '<input type="text" class="context-input discussion-reply-input" id="replyInput' + d.id + '" placeholder="' + t('placeholders.replyDots') + '" style="flex: 1; font-size: 12px; padding: 4px 8px;" onkeydown="if(event.key===\'Enter\'){replyToDiscussion(' + d.id + ');}">' +
        '<button class="btn btn-sm" onclick="replyToDiscussion(' + d.id + ')">' + t('buttons.reply') + '</button>' +
        '</div>'
      : '';

    div.innerHTML =
      '<div class="qa-header">' +
        '<span class="qa-id">#' + d.id + '</span>' +
        authorBadge + typeBadge +
        '<span class="qa-question">' + escapeHtml(d.text) + '</span>' +
        researchLink + statusBadge + hideBtn +
        '<button class="qa-delete" onclick="deleteDiscussion(' + d.id + ')" title="' + t('buttons.delete') + '">&times;</button>' +
      '</div>' +
      repliesHtml +
      replyForm +
      (d.created_at ? '<div class="qa-time">' + formatTime(d.created_at) + '</div>' : '');
    container.appendChild(div);
  });

  // Show hidden toggle
  if (hiddenCount > 0) {
    var toggle = document.createElement('div');
    toggle.style.cssText = 'text-align:center;margin-top:8px;';
    toggle.innerHTML = '<button class="btn btn-sm" onclick="toggleHiddenDiscussions()">' +
      (showHidden ? t('discussions.hideHidden', {count: hiddenCount}) : t('discussions.showHidden', {count: hiddenCount})) + '</button>';
    container.appendChild(toggle);
  }
}

function renderContextRaw() {
  var pre = document.getElementById('contextRaw');
  if (pre) {
    pre.textContent = JSON.stringify(CONTEXT_DATA, null, 2);
  }
}

function saveContext() {
  var nameInput = document.getElementById('contextTicketName');
  var textArea = document.getElementById('contextText');

  CONTEXT_DATA.ticket_name = nameInput ? nameInput.value : '';
  CONTEXT_DATA.context = textArea ? textArea.value : '';

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context', {
    ticket_name: CONTEXT_DATA.ticket_name,
    context: CONTEXT_DATA.context,
    refs: CONTEXT_DATA.refs || []
  }).then(function() {
    renderContextRaw();
    showToast(t('messages.contextSaved'));
  }).catch(function(e) {
    showToast(t('messages.failedToSave', {error: e.message}));
  });
}

function addNewDiscussion() {
  var input = document.getElementById('newDiscussionInput');
  if (!input || !input.value.trim()) return;

  var text = input.value.trim();
  input.value = '';

  var typeSelect = document.getElementById('newDiscussionType');
  var type = typeSelect ? typeSelect.value : 'general';

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context/discussions', {
    text: text,
    type: type
  }).then(function(res) {
    CONTEXT_DATA.discussions.push({
      id: res.id,
      text: text,
      type: type,
      replies: [],
      author: 'user',
      status: 'open',
      hidden: 0,
      created_at: new Date().toISOString()
    });
    renderDiscussions();
    renderContextRaw();
  }).catch(function(e) {
    showToast(t('messages.failedToAddDiscussion', {error: e.message}));
  });
}

function deleteDiscussion(discussionId) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiDelete('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context/discussions/' + discussionId)
    .then(function() {
      CONTEXT_DATA.discussions = CONTEXT_DATA.discussions.filter(function(d) { return d.id !== discussionId; });
      renderDiscussions();
      renderContextRaw();
    }).catch(function(e) {
      showToast(t('messages.failedToDelete', {error: e.message}));
    });
}

function resolveDiscussion(discussionId, unresolve) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context/discussions/' + discussionId, {
    status: unresolve ? 'open' : 'resolved'
  }).then(function() {
    var d = CONTEXT_DATA.discussions.find(function(d) { return d.id === discussionId; });
    if (d) d.status = unresolve ? 'open' : 'resolved';
    renderDiscussions();
    renderPPDiscussions();
    renderContextRaw();
    showToast(t('messages.discussionResolved'));
  }).catch(function(e) {
    showToast(t('messages.failedToResolve', {error: e.message}));
  });
}

function replyToDiscussion(discussionId) {
  var input = document.getElementById('replyInput' + discussionId);
  if (!input) return;
  var text = input.value.trim();
  if (!text) return;

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context/discussions/' + discussionId + '/reply', {text: text})
    .then(function() {
      input.value = '';
      refreshContext();
    });
}

function hideDiscussion(discussionId, hide) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/discussions/' + discussionId + '/hide', {
    hidden: hide
  }).then(function() {
    var d = CONTEXT_DATA.discussions.find(function(d) { return d.id === discussionId; });
    if (d) d.hidden = hide ? 1 : 0;
    renderDiscussions();
  }).catch(function(e) {
    showToast(t('messages.failedToUpdate', {error: e.message}));
  });
}

function toggleHiddenDiscussions() {
  var container = document.getElementById('discussionsList');
  if (!container) return;
  container.dataset.showHidden = container.dataset.showHidden === 'true' ? 'false' : 'true';
  renderDiscussions();
}

function goToResearch(discussionId) {
  // Switch to Research tab in sidebar
  var sidebarBtns = document.querySelectorAll('.sidebar-btn');
  // Find Research tab button (index varies, use title)
  var researchTab = Array.from(document.querySelectorAll('.tab-btn')).find(function(b) { return b.textContent.trim() === 'Research'; });
  if (researchTab) researchTab.click();
  // Highlight the linked research
  setTimeout(function() {
    var researchGroups = document.querySelectorAll('.research-group');
    researchGroups.forEach(function(g) {
      var rid = g.dataset.discussionId;
      if (rid && parseInt(rid) === discussionId) {
        g.classList.remove('collapsed');
        g.scrollIntoView({ behavior: 'smooth', block: 'center' });
        g.style.outline = '2px solid var(--warning)';
        setTimeout(function() { g.style.outline = ''; }, 3000);
      }
    });
  }, 300);
}

function refreshContext() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context')
    .then(function(data) {
      if (data) {
        CONTEXT_DATA = data;
        renderContext();
      }
    });
}

function formatTime(iso) {
  if (!iso) return '';
  try {
    var d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return iso;
  }
}

// ═══════════════════════════════════════════════
//  FILE REFERENCES
// ═══════════════════════════════════════════════

function renderContextRefs() {
  var list = document.getElementById('contextRefsList');
  if (!list) return;
  var refs = CONTEXT_DATA.refs || [];
  list.innerHTML = refs.map(function(ref, i) {
    var icon = ref.endsWith('/') ? '📁' : '📄';
    return '<span class="ref-chip">' + icon + ' ' + escapeHtml(ref) + '<span class="ref-remove" onclick="removeContextRef(' + i + ')">&times;</span></span>';
  }).join('');
}

var _refSearchTimeout = null;

function searchContextRefs(query) {
  var dropdown = document.getElementById('contextRefDropdown');
  clearTimeout(_refSearchTimeout);
  if (!query || query.length < 2) {
    dropdown.style.display = 'none';
    return;
  }
  _refSearchTimeout = setTimeout(function() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/search-paths?q=' + encodeURIComponent(query))
      .then(function(data) {
        if (!data || !data.results || data.results.length === 0) {
          dropdown.style.display = 'none';
          return;
        }
        var existing = {};
        (CONTEXT_DATA.refs || []).forEach(function(r) { existing[r] = true; });
        var filtered = data.results.filter(function(r) { return !existing[r]; });
        if (filtered.length === 0) {
          dropdown.style.display = 'none';
          return;
        }
        dropdown.innerHTML = filtered.map(function(r) {
          var icon = r.endsWith('/') ? '📁' : '📄';
          return '<div class="ref-dropdown-item" onclick="addContextRef(\'' + r.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + '\')"><span class="ref-icon">' + icon + '</span>' + escapeHtml(r) + '</div>';
        }).join('');
        dropdown.style.display = 'block';
      }).catch(function() {
        dropdown.style.display = 'none';
      });
  }, 200);
}

function addContextRef(path) {
  if (!CONTEXT_DATA.refs) CONTEXT_DATA.refs = [];
  if (!CONTEXT_DATA.refs.includes(path)) {
    CONTEXT_DATA.refs.push(path);
    renderContextRefs();
    renderContextRaw();
  }
  var search = document.getElementById('contextRefSearch');
  var dropdown = document.getElementById('contextRefDropdown');
  if (search) search.value = '';
  if (dropdown) dropdown.style.display = 'none';
}

function addManualContextRef(path) {
    path = path.trim();
    if (!path) return;
    if (CONTEXT_DATA.refs.includes(path)) return;
    CONTEXT_DATA.refs.push(path);
    renderContextRefs();
    renderContextRaw();
    document.getElementById('contextRefSearch').value = '';
    document.getElementById('contextRefDropdown').style.display = 'none';
}

function removeContextRef(index) {
  if (!CONTEXT_DATA.refs) return;
  CONTEXT_DATA.refs.splice(index, 1);
  renderContextRefs();
  renderContextRaw();
}

document.addEventListener('click', function(e) {
  var dropdown = document.getElementById('contextRefDropdown');
  var search = document.getElementById('contextRefSearch');
  if (dropdown && search && !search.contains(e.target) && !dropdown.contains(e.target)) {
    dropdown.style.display = 'none';
  }
});

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

function loadClaudeCommand() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/command')
    .then(function(r) { return r.json(); })
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

  fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/command', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      claude_command: cmd,
      skip_permissions: skip,
      restrict_to_workspace: restrictCheck ? restrictCheck.checked : true,
      allowed_external_paths: pathsInput ? pathsInput.value.trim() : '/tmp/'
    })
  })
  .then(function(r) { return r.json(); })
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

function showToast(message) {
  var existing = document.getElementById('toast');
  if (existing) existing.remove();

  var toast = document.createElement('div');
  toast.id = 'toast';
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(function() { toast.classList.add('show'); }, 10);
  setTimeout(function() {
    toast.classList.remove('show');
    setTimeout(function() { toast.remove(); }, 300);
  }, 2000);
}
