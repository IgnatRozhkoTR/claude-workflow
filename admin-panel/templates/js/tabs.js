// ═══════════════════════════════════════════════
//  TABS
// ═══════════════════════════════════════════════
var _explorerLoaded = false;
var _initialLoad = true;

async function refreshTabData() {
  if (_initialLoad) return;
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  try {
    var stateData = await apiGetState(ctx.projectId, ctx.branch);
    applyStateData(stateData);
    LOCK_DATA.session_id = stateData.session_id || null;
    LOCK_DATA.working_dir = stateData.working_dir || null;
    LOCK_DATA.sessions = stateData.sessions || [];
  } catch(e) { console.warn('Refresh state failed:', e.message); }
  try {
    var diffData = await apiGetDiff(ctx.projectId, ctx.branch, state.diffSource);
    if (diffData && diffData.files) DIFF_DATA = diffData;
  } catch(e) { console.warn('Refresh diff failed:', e.message); }
  try {
    var contextData = await apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/context');
    if (contextData) CONTEXT_DATA = contextData;
  } catch(e) { console.warn('Refresh context failed:', e.message); }
}

async function switchTab(tabId) {
  var mainEl = document.querySelector('.main');
  if (mainEl) {
    if (tabId === 'terminal') {
      mainEl.classList.add('terminal-active');
    } else {
      mainEl.classList.remove('terminal-active');
    }
  }

  // Deactivate all top tab buttons
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
  // Deactivate all sidebar buttons
  document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
  // Show the correct panel
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tabId));
  history.replaceState(null, '', '#' + tabId);

  await refreshTabData();

  if (tabId === 'dashboard') {
    if (typeof renderContext === 'function') renderContext();
  } else if (tabId === 'plan') {
    if (typeof renderPlan === 'function') renderPlan();
    if (typeof renderScope === 'function') renderScope();
    if (typeof renderPhaseActions === 'function') renderPhaseActions();
    if (typeof updateScopeStatusUI === 'function') updateScopeStatusUI(LOCK_DATA.scope_status || 'pending');
    if (typeof updatePlanApprovalUI === 'function') updatePlanApprovalUI(LOCK_DATA.plan_status || 'pending');
    if (typeof loadCriteria === 'function') loadCriteria();
  } else if (tabId === 'preplanning') {
    if (typeof renderPreplanning === 'function') renderPreplanning();
  } else if (tabId === 'research') {
    if (typeof renderResearch === 'function') renderResearch();
  } else if (tabId === 'phases') {
    if (typeof renderPhaseBar === 'function') renderPhaseBar('phaseBarControl', 'phaseLabelsControl');
    if (typeof renderPhaseHistory === 'function') renderPhaseHistory();
    if (typeof renderPhaseActions === 'function') renderPhaseActions();
    if (typeof renderApprovalStatus === 'function') renderApprovalStatus();
  } else if (tabId === 'changes') {
    if (typeof renderFileList === 'function') renderFileList();
  } else if (tabId === 'review') {
    if (typeof loadReviewComments === 'function') loadReviewComments();
  } else if (tabId === 'files') {
    if (!_explorerLoaded && typeof loadExplorerFiles === 'function') {
      _explorerLoaded = true;
      loadExplorerFiles();
    }
  } else if (tabId === 'terminal') {
    if (typeof onTerminalTabActivated === 'function') onTerminalTabActivated();
  }
}

// Top tab bar buttons
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// Sidebar buttons
document.querySelectorAll('.sidebar-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// Restore tab from URL hash on load (sync-only, no data refresh)
(function() {
  var hash = location.hash.replace('#', '');
  if (hash && document.getElementById('panel-' + hash)) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === hash));
    document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === hash));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + hash));
  }
})();
