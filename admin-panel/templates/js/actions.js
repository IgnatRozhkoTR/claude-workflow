// ═══════════════════════════════════════════════
//  USER GATE ACTIONS
// ═══════════════════════════════════════════════

async function handleApprove() {
  var ctx = getWorkspaceContext();
  if (!ctx) { showToast(t('errors.workspaceNotSelected')); return; }

  var nonceResp = await apiGetGateNonce(ctx.projectId, ctx.branch);
  var token = nonceResp.nonce;
  if (!token) { showToast(t('errors.noApprovalGateActive')); return; }

  var commitMessage = '';
  var input = document.getElementById('commitMessageInput');
  if (input) commitMessage = input.value.trim();

  try {
    var result = await apiApprove(ctx.projectId, ctx.branch, token, commitMessage);
    showToast(t('messages.approved', {phase: result.phase}));
    await refreshState();
  } catch (e) {
    showToast(t('messages.approveFailed', {error: e.message}));
  }
}

async function handleReject(feedback) {
  var ctx = getWorkspaceContext();
  if (!ctx) { showToast(t('errors.workspaceNotSelected')); return; }

  var comments = feedback || '';

  var nonceResp = await apiGetGateNonce(ctx.projectId, ctx.branch);
  var token = nonceResp.nonce;
  if (!token) { showToast(t('errors.noApprovalGateActive')); return; }

  try {
    var result = await apiReject(ctx.projectId, ctx.branch, token, comments);
    showToast(t('messages.rejected', {phase: result.phase}));
    await refreshState();
  } catch (e) {
    showToast(t('messages.rejectFailed', {error: e.message}));
  }
}

async function handleRejectWithInput() {
  var input = document.getElementById('rejectFeedbackInput');
  var feedback = input ? input.value.trim() : '';
  await handleReject(feedback);
}

function _updateApprovalUI(badgeId, approveBtnId, rejectBtnId, setStatus, status) {
  var badge = document.getElementById(badgeId);
  var approveBtn = document.getElementById(approveBtnId);
  var rejectBtn = document.getElementById(rejectBtnId);
  if (!badge || !approveBtn || !rejectBtn) return;

  approveBtn.style.display = '';
  rejectBtn.style.display = '';

  if (status === 'approved') {
    badge.textContent = t('badges.approved');
    badge.className = 'badge badge-success';
    approveBtn.textContent = t('buttons.revokeApproval');
    approveBtn.className = 'btn btn-sm btn-outline';
    approveBtn.onclick = function() { setStatus('pending'); };
    rejectBtn.textContent = t('buttons.reject');
    rejectBtn.className = 'btn btn-sm btn-danger-outline';
    rejectBtn.onclick = function() { setStatus('rejected'); };
  } else if (status === 'rejected') {
    badge.textContent = t('badges.rejected');
    badge.className = 'badge badge-danger';
    approveBtn.textContent = t('buttons.approve');
    approveBtn.className = 'btn btn-sm btn-primary';
    approveBtn.onclick = function() { setStatus('approved'); };
    rejectBtn.textContent = t('buttons.revokeRejection');
    rejectBtn.className = 'btn btn-sm btn-outline';
    rejectBtn.onclick = function() { setStatus('pending'); };
  } else {
    badge.textContent = t('badges.pending');
    badge.className = 'badge badge-warning';
    approveBtn.textContent = t('buttons.approve');
    approveBtn.className = 'btn btn-sm btn-primary';
    approveBtn.onclick = function() { setStatus('approved'); };
    rejectBtn.textContent = t('buttons.reject');
    rejectBtn.className = 'btn btn-sm btn-danger-outline';
    rejectBtn.onclick = function() { setStatus('rejected'); };
  }
}

function updateScopeStatusUI(status) {
  _updateApprovalUI('scopeStatusBadge', 'scopeApproveBtn', 'scopeRejectBtn', setScopeStatus, status);
}

async function setScopeStatus(status) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    await apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/scope-status', {status: status});
    LOCK_DATA.scope_status = status;
    if (status === 'approved') {
      updateScopeStatusUI(status);
      await tryAutoAdvanceGate();
    } else {
      updateScopeStatusUI(status);
    }
  } catch (e) {
    console.error('Failed to set scope status:', e);
  }
}

function updatePlanApprovalUI(status) {
  var restoreBtn = document.getElementById('planRestoreBtn');
  if (restoreBtn) {
    restoreBtn.style.display = LOCK_DATA.has_prev_plan ? '' : 'none';
  }
  _updateApprovalUI('planStatusBadge', 'planApproveBtn', 'planRejectBtn', setPlanStatus, status);
}

async function setPlanStatus(status) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    await apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/plan-status', {status: status});
    LOCK_DATA.plan_status = status;
    if (status === 'approved') {
      updatePlanApprovalUI(status);
      await tryAutoAdvanceGate();
    } else {
      updatePlanApprovalUI(status);
    }
  } catch (e) {
    console.error('Failed to set plan status:', e);
  }
}

async function tryAutoAdvanceGate() {
  if (state.phase !== '2.1') return;
  if (LOCK_DATA.plan_status !== 'approved' || LOCK_DATA.scope_status !== 'approved') return;

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    var nonceResp = await apiGetGateNonce(ctx.projectId, ctx.branch);
    var token = nonceResp.nonce;
    if (!token) return;

    var result = await apiApprove(ctx.projectId, ctx.branch, token, '');
    showToast(t('messages.approved', {phase: result.phase}));
    await refreshState();
  } catch (e) {
    console.log('Auto-advance failed, use Phase Control:', e.message);
  }
}

async function refreshState() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var refreshBtn = document.querySelector('.header-refresh-btn');
  if (refreshBtn) refreshBtn.classList.add('refreshing');

  try {
    var stateData = await apiGetState(ctx.projectId, ctx.branch);

    applyStateData(stateData);

    document.getElementById('phaseLabel').textContent = t('phase.label', {phase: state.phase, name: getPhaseName(state.phase)});

    var yoloCheck = document.getElementById('yoloCheck');
    if (yoloCheck) yoloCheck.checked = !!LOCK_DATA.yolo_mode;

    updateScopeStatusUI(LOCK_DATA.scope_status || 'pending');
    updatePlanApprovalUI(LOCK_DATA.plan_status || 'pending');

    try {
      var diffData = await apiGetDiff(ctx.projectId, ctx.branch, state.diffSource);
      if (diffData && diffData.files) {
        AppState.diff = diffData;
        DIFF_DATA = AppState.diff;
      }
    } catch (de) {
      console.warn('Failed to refresh diff:', de.message);
    }

    EventBus.emit('state:refreshed', stateData);
  } catch (e) {
    console.warn('Failed to refresh state:', e.message);
  } finally {
    if (refreshBtn) refreshBtn.classList.remove('refreshing');
  }
}

async function restorePlan() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    await apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/restore-plan', {});
    showToast(t('messages.previousPlanRestored'));
    await refreshState();
  } catch (e) {
    showToast(t('messages.restoreFailed', {error: e.message}));
  }
}
