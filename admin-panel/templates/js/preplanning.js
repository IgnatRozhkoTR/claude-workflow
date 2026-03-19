// ═══════════════════════════════════════════════
//  PRE-PLANNING TAB
// ═══════════════════════════════════════════════

function renderPreplanning() {
  renderPPResearchSummaries();
  renderPPImpactAnalysis();
  renderPPDiscussions();
  renderPPGateActions();
}

// ═══════════════════════════════════════════════
//  RESEARCH SUMMARIES
// ═══════════════════════════════════════════════

function renderPPResearchSummaries() {
  var container = document.getElementById('ppResearchList');
  if (!container) return;
  container.innerHTML = '';

  if (!RESEARCH_DATA || RESEARCH_DATA.length === 0) {
    container.innerHTML = '<div class="no-items-msg">' + t('preplanning.noResearch') + '</div>';
    return;
  }

  RESEARCH_DATA.forEach(function(entry) {
    var topicName = entry.topic || t('research.untitledResearch');
    var summary = entry.summary || '';
    var proven = entry.proven;
    var badgeClass = proven === 1 ? 'success' : proven === -1 ? 'danger' : 'warning';
    var badgeText = proven === 1 ? t('badges.verified') : proven === -1 ? t('badges.rejected') : t('badges.pending');

    var card = document.createElement('div');
    card.className = 'pp-research-card';
    card.dataset.entryId = entry.id;

    var bodyDiv = document.createElement('div');
    bodyDiv.className = 'pp-research-card-body';
    bodyDiv.innerHTML =
      '<div class="pp-research-topic">' + escapeHtml(topicName) + '</div>' +
      (summary ? '<div class="pp-research-summary">' + escapeHtml(summary) + '</div>' : '');

    bodyDiv.addEventListener('click', function(e) {
      if (e.target.closest('.pp-comment-btn, .pp-inline-comment-form')) return;
      navigateToResearchEntry(entry);
    });

    var actionsDiv = document.createElement('div');
    actionsDiv.className = 'pp-research-actions';
    actionsDiv.innerHTML =
      '<span class="badge badge-' + badgeClass + '">' + badgeText + '</span>' +
      '<button class="pp-comment-btn" onclick="event.stopPropagation(); togglePPInlineComment(this, \'research\', ' + entry.id + ')" title="' + t('comments.addComment') + '">\u{1F4AC}</button>';

    card.appendChild(bodyDiv);
    card.appendChild(actionsDiv);
    container.appendChild(card);
  });
}

function navigateToResearchEntry(entry) {
  switchTab('research');
  setTimeout(function() {
    var groups = document.querySelectorAll('.research-group');
    groups.forEach(function(g) {
      var titleEl = g.querySelector('.research-group-title');
      if (titleEl && titleEl.textContent === (entry.topic || '')) {
        g.classList.remove('collapsed');
        g.scrollIntoView({ behavior: 'smooth', block: 'center' });
        g.style.outline = '2px solid var(--accent)';
        setTimeout(function() { g.style.outline = ''; }, 3000);
      }
    });
  }, 350);
}

// ═══════════════════════════════════════════════
//  IMPACT ANALYSIS
// ═══════════════════════════════════════════════

function renderPPImpactAnalysis() {
  var container = document.getElementById('ppImpactContent');
  if (!container) return;
  container.innerHTML = '';

  var data = window.IMPACT_DATA;
  if (!data) {
    container.innerHTML = '<div class="pp-impact-empty">' + t('preplanning.noImpactAnalysis') + '</div>';
    return;
  }

  var sections = [
    { key: 'affected_flows', label: t('impact.affectedFlows') },
    { key: 'api_changes', label: t('impact.apiChanges') },
    { key: 'data_flow_changes', label: t('impact.dataFlowChanges') },
    { key: 'external_dependencies', label: t('impact.externalDeps') },
    { key: 'ticket_gaps', label: t('impact.ticketGaps') },
    { key: 'open_questions', label: t('impact.openQuestions') },
  ];

  sections.forEach(function(s) {
    var text = data[s.key];
    if (!text) return;

    var section = document.createElement('div');
    section.className = 'pp-impact-section';
    section.innerHTML =
      '<div class="pp-impact-label" style="display: flex; justify-content: space-between; align-items: center;">' +
        '<span>' + s.label + '</span>' +
        '<button class="pp-comment-btn" onclick="togglePPInlineComment(this, \'impact\', \'' + s.key + '\')" title="' + t('comments.addComment') + '">\u{1F4AC}</button>' +
      '</div>' +
      '<div class="pp-impact-text">' + (typeof marked !== 'undefined' ? marked.parse(text) : escapeHtml(text)) + '</div>';
    container.appendChild(section);
  });

  if (container.children.length === 0) {
    container.innerHTML = '<div class="pp-impact-empty">' + t('preplanning.noImpactAnalysis') + '</div>';
  }
}

// ═══════════════════════════════════════════════
//  DISCUSSIONS
// ═══════════════════════════════════════════════

var ppShowResolved = false;
var ppShowProven = false;

function togglePPResolved() {
  ppShowResolved = !ppShowResolved;
  var btn = document.getElementById('ppToggleResolved');
  if (btn) btn.textContent = ppShowResolved ? t('discussions.hideResolved') : t('discussions.showResolved');
  renderPPDiscussions();
}

function togglePPProven() {
  ppShowProven = !ppShowProven;
  var btn = document.getElementById('ppToggleProven');
  if (btn) btn.textContent = ppShowProven ? t('discussions.hideProven') : t('discussions.showProven');
  renderPPDiscussions();
}

function isResearchProven(discussionId) {
  if (!RESEARCH_DATA) return false;
  for (var i = 0; i < RESEARCH_DATA.length; i++) {
    if (RESEARCH_DATA[i].discussion_id === discussionId) {
      return RESEARCH_DATA[i].proven === 1;
    }
  }
  return false;
}

function renderPPDiscussions() {
  var container = document.getElementById('ppDiscussionsList');
  if (!container) return;
  container.innerHTML = '';

  var discussions = CONTEXT_DATA.discussions || [];

  var badge = document.getElementById('ppDiscussionsBadge');
  if (badge) {
    var openCount = discussions.filter(function(d) { return d.status === 'open'; }).length;
    badge.textContent = openCount > 0 ? openCount : discussions.length;
    badge.className = 'badge ' + (openCount > 0 ? 'badge-warning' : 'badge-success');
  }

  var researchBadge = document.getElementById('ppResearchDiscBadge');
  if (researchBadge) {
    var researchPending = discussions.filter(function(d) { return d.type === 'research' && !isResearchProven(d.id); }).length;
    if (researchPending > 0) {
      researchBadge.textContent = t('badges.researchCount', {count: researchPending});
      researchBadge.style.display = '';
    } else {
      researchBadge.style.display = 'none';
    }
  }

  if (discussions.length === 0) {
    container.innerHTML = '<div class="no-items-msg">' + t('discussions.noItems') + '</div>';
    return;
  }

  var sorted = discussions.slice().sort(function(a, b) {
    if (a.status === 'open' && b.status !== 'open') return -1;
    if (a.status !== 'open' && b.status === 'open') return 1;
    return 0;
  });

  sorted.forEach(function(d) {
    var isResearch = d.type === 'research';
    var isResolved = d.status === 'resolved';
    var proven = isResearch ? isResearchProven(d.id) : false;

    if (isResearch && proven && !ppShowProven) return;
    if (!isResearch && isResolved && !ppShowResolved) return;

    var div = document.createElement('div');
    div.className = 'pp-discussion-item' + (isResolved || proven ? ' pp-resolved' : '');

    var author = d.author || 'user';
    var authorBadge = '<span class="qa-author qa-author-' + author + '">' + author + '</span>';

    var typeBadge = isResearch
      ? '<span class="badge" style="font-size:0.6rem;background:var(--warning-dim);color:var(--warning);">' + t('badges.research') + '</span>'
      : '<span class="badge" style="font-size:0.6rem;background:var(--info-dim);color:var(--info);">' + t('discussionType.general') + '</span>';

    var statusBadge;
    if (isResearch) {
      statusBadge = proven
        ? '<span class="badge badge-success" style="font-size:0.65rem;">' + t('badges.verified') + '</span>'
        : '<span class="badge badge-warning" style="font-size:0.65rem;">' + t('badges.pending') + '</span>';
    } else {
      statusBadge = isResolved
        ? '<span class="badge badge-success" style="font-size:0.65rem;">' + t('badges.resolved') + '</span>'
        : '<span class="badge badge-warning" style="font-size:0.65rem;">' + t('badges.open') + '</span>';
    }

    var resolveBtn = isResolved
      ? '<button class="btn btn-sm" style="font-size:0.65rem;padding:1px 6px" onclick="resolveDiscussion(' + d.id + ', true)">' + t('buttons.unresolve') + '</button>'
      : '<button class="btn btn-sm" style="font-size:0.65rem;padding:1px 6px" onclick="resolveDiscussion(' + d.id + ')">' + t('buttons.resolve') + '</button>';

    div.innerHTML =
      '<div class="pp-discussion-header">' +
        '<span class="qa-id">#' + d.id + '</span>' +
        authorBadge +
        '<span class="pp-discussion-text">' + escapeHtml(d.text) + '</span>' +
        '<div class="pp-discussion-meta">' + typeBadge + statusBadge + resolveBtn + '</div>' +
      '</div>';

    if (d.replies && d.replies.length > 0) {
      var repliesHtml = '<div style="margin-top: 6px; padding-left: 16px; border-left: 2px solid var(--border);">';
      d.replies.forEach(function(reply) {
        var replyAuthorBadge = reply.author === 'agent'
          ? '<span class="badge badge-accent" style="font-size: 10px;">' + t('author.agent') + '</span>'
          : '<span class="badge" style="font-size: 10px;">' + t('author.user') + '</span>';
        repliesHtml += '<div style="padding: 4px 0; font-size: 13px;">' + replyAuthorBadge + ' ' + escapeHtml(reply.text) + '</div>';
      });
      repliesHtml += '</div>';
      div.innerHTML += repliesHtml;
    }

    if (d.status !== 'resolved') {
      div.innerHTML +=
        '<div style="margin-top: 6px; display: flex; gap: 4px;">' +
          '<input type="text" class="context-input" id="ppReplyInput' + d.id + '" placeholder="' + t('placeholders.reply') + '" style="flex:1; font-size: 0.78rem; padding: 4px 8px;" onkeydown="if(event.key===\'Enter\'){event.preventDefault();ppReplyToDiscussion(' + d.id + ');}">' +
          '<button class="btn btn-sm" style="font-size:0.65rem;padding:2px 8px;" onclick="ppReplyToDiscussion(' + d.id + ')">' + t('buttons.reply') + '</button>' +
        '</div>';
    }

    container.appendChild(div);
  });
}

function addPPDiscussion() {
  var input = document.getElementById('ppNewDiscussionInput');
  if (!input || !input.value.trim()) return;

  var text = input.value.trim();
  input.value = '';

  var typeSelect = document.getElementById('ppNewDiscussionType');
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
    renderPPDiscussions();
    renderDiscussions();
  }).catch(function(e) {
    showToast(t('messages.failedToAddDiscussion', { error: e.message }));
  });
}

// ═══════════════════════════════════════════════
//  GATE APPROVE / REJECT (Phase 1.4)
// ═══════════════════════════════════════════════

function renderPPGateActions() {
  var container = document.getElementById('ppGateActions');
  if (!container) return;

  if (state.phase !== '1.4') {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = '';
  container.innerHTML =
    '<div class="pp-section-title">' + t('preplanning.preplanningApproval') + '</div>' +
    '<p style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 10px;">' + t('preplanning.approvalDescription') + '</p>' +
    '<textarea id="ppRejectFeedback" placeholder="' + t('placeholders.feedbackForChanges') + '" style="font-family: var(--font-mono); font-size: 0.82rem; padding: 8px 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-primary); outline: none; resize: vertical; min-height: 50px; width: 100%; margin-bottom: 10px;"></textarea>' +
    '<div class="pp-gate-actions">' +
      '<button class="btn btn-primary" onclick="ppApprove()">' + t('preplanning.approvePreplanning') + '</button>' +
      '<button class="btn btn-danger" onclick="ppReject()">' + t('preplanning.rejectPreplanning') + '</button>' +
    '</div>';
}

async function ppApprove() {
  var ctx = getWorkspaceContext();
  if (!ctx) { showToast(t('errors.workspaceNotSelected')); return; }

  var nonceResp = await apiGetGateNonce(ctx.projectId, ctx.branch);
  var token = nonceResp.nonce;
  if (!token) { showToast(t('errors.noApprovalGateActive')); return; }

  try {
    var result = await apiApprove(ctx.projectId, ctx.branch, token, '');
    showToast(t('messages.approved', { phase: result.phase }));
    await refreshState();
  } catch (e) {
    showToast(t('messages.approveFailed', { error: e.message }));
  }
}

async function ppReject() {
  var ctx = getWorkspaceContext();
  if (!ctx) { showToast(t('errors.workspaceNotSelected')); return; }

  var feedback = '';
  var textarea = document.getElementById('ppRejectFeedback');
  if (textarea) feedback = textarea.value.trim();

  var nonceResp = await apiGetGateNonce(ctx.projectId, ctx.branch);
  var token = nonceResp.nonce;
  if (!token) { showToast(t('errors.noApprovalGateActive')); return; }

  try {
    var result = await apiReject(ctx.projectId, ctx.branch, token, feedback);
    showToast(t('messages.rejected', { phase: result.phase }));
    await refreshState();
  } catch (e) {
    showToast(t('messages.rejectFailed', { error: e.message }));
  }
}

// ═══════════════════════════════════════════════
//  INLINE COMMENTING
// ═══════════════════════════════════════════════

function togglePPInlineComment(btn, scope, targetId) {
  var card = btn.closest('.pp-research-card, .pp-impact-section, .card-body, #ppImpactContent');
  if (!card) card = btn.parentElement;

  var existingForm = card.querySelector('.pp-inline-comment-form');
  if (existingForm) {
    existingForm.remove();
    return;
  }

  document.querySelectorAll('.pp-inline-comment-form').forEach(function(el) { el.remove(); });

  var form = document.createElement('div');
  form.className = 'pp-inline-comment-form';
  form.onclick = function(e) { e.stopPropagation(); };

  var target = scope + ':' + targetId;

  form.innerHTML =
    '<input type="text" placeholder="' + t('comments.addComment') + '" ' +
      'onkeydown="if(event.key===\'Enter\'){event.preventDefault();submitPPComment(this, \'' + escapeAttr(scope) + '\', \'' + escapeAttr(String(targetId)) + '\');}">' +
    '<button class="btn btn-sm" onclick="submitPPComment(this.previousElementSibling, \'' + escapeAttr(scope) + '\', \'' + escapeAttr(String(targetId)) + '\')">' + t('comments.save') + '</button>';

  card.appendChild(form);
  form.querySelector('input').focus();
}

function submitPPComment(inputEl, scope, targetId) {
  var text = inputEl.value.trim();
  if (!text) return;

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context/discussions', {
    text: text,
    type: scope,
    scope: scope,
    target: targetId
  }).then(function(res) {
    CONTEXT_DATA.discussions.push({
      id: res.id,
      text: text,
      type: scope,
      scope: scope,
      target: targetId,
      replies: [],
      author: 'user',
      status: 'open',
      hidden: 0,
      created_at: new Date().toISOString()
    });
    renderPPDiscussions();
    renderDiscussions();
    inputEl.value = '';
    var form = inputEl.closest('.pp-inline-comment-form');
    if (form) form.remove();
    showToast(t('preplanning.commentAdded'));
  }).catch(function(e) {
    showToast(t('messages.failedToAddDiscussion', { error: e.message }));
  });
}

function ppReplyToDiscussion(discussionId) {
  var input = document.getElementById('ppReplyInput' + discussionId);
  if (!input) return;
  var text = input.value.trim();
  if (!text) return;

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context/discussions/' + discussionId + '/reply', {
    text: text
  }).then(function(res) {
    var discussions = CONTEXT_DATA.discussions || [];
    for (var i = 0; i < discussions.length; i++) {
      if (discussions[i].id === discussionId) {
        if (!discussions[i].replies) discussions[i].replies = [];
        discussions[i].replies.push({ text: text, author: 'user' });
        break;
      }
    }
    renderPPDiscussions();
    renderDiscussions();
  }).catch(function(e) {
    showToast(t('messages.failedToAddDiscussion', { error: e.message }));
  });
}
