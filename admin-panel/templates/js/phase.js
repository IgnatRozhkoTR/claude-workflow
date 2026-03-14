// ═══════════════════════════════════════════════
//  PHASE HISTORY LOG
// ═══════════════════════════════════════════════
function renderPhaseHistory() {
  var container = document.getElementById('phaseHistoryLog');
  if (!container) return;

  var history = window.PHASE_HISTORY || [];
  if (history.length === 0) {
    container.innerHTML = '<div class="phase-history-empty">' + t('phase.noChangesRecorded') + '</div>';
    return;
  }

  container.innerHTML = history
    .slice()
    .reverse()
    .map(function(entry) {
      return '<div class="phase-history-entry">' + entry.from + ' → ' + entry.to + ' — ' + entry.time + '</div>';
    })
    .join('');
}

// ═══════════════════════════════════════════════
//  PHASE BAR
// ═══════════════════════════════════════════════

function getPhaseSequenceForBar() {
  var fixedBefore = ['0', '1.0', '1.1', '1.2', '1.3', '2.0', '2.1'];
  var fixedAfter = ['4.0', '4.1', '4.2', '5'];

  var plan = LOCK_DATA.plan;
  var execPhases = [];
  if (plan && plan.execution && plan.execution.length > 0) {
    plan.execution.forEach(function(item) {
      var n = item.id.split('.').pop();
      for (var k = 0; k <= 4; k++) {
        execPhases.push('3.' + n + '.' + k);
      }
    });
  } else {
    execPhases = ['3.N'];
  }

  return fixedBefore.concat(execPhases).concat(fixedAfter);
}

function getPhaseBarSegments() {
  var seq = getPhaseSequenceForBar();
  var segments = [];
  var groups = {};

  seq.forEach(function(p) {
    var match = p.match(/^3\.(\d+)\.(\d+)$/);
    if (match) {
      var n = match[1];
      if (!groups[n]) {
        groups[n] = { phases: [], startIndex: segments.length };
        var plan = PLAN_DATA || {};
        var execution = plan.execution || [];
        var sub = execution.find(function(e) { return e.id === "3." + n; });
        segments.push({
          type: "group",
          label: sub ? sub.name : "3." + n,
          id: "3." + n,
          phases: [],
          gate: true
        });
      }
      segments[groups[n].startIndex].phases.push(p);
    } else {
      segments.push({
        type: "single",
        phase: p,
        label: getPhaseName(p),
        gate: isUserGate(p)
      });
    }
  });

  return segments;
}

function renderPhaseBar(barId, labelsId) {
  var bar = document.getElementById(barId);
  var labels = document.getElementById(labelsId);
  if (!bar || !labels) return;
  bar.innerHTML = '';
  labels.innerHTML = '';

  var segments = getPhaseBarSegments();
  var seq = getPhaseSequenceForBar();
  var currentIdx = seq.indexOf(state.phase);

  segments.forEach(function(seg) {
    var div = document.createElement('div');
    div.className = 'phase-segment';

    if (seg.type === "single") {
      var idx = seq.indexOf(seg.phase);
      if (idx < currentIdx) div.classList.add('filled');
      if (seg.phase === state.phase) div.classList.add('current');
      div.title = getPhaseName(seg.phase);
    } else {
      var groupPhases = seg.phases;
      var firstIdx = seq.indexOf(groupPhases[0]);
      var lastIdx = seq.indexOf(groupPhases[groupPhases.length - 1]);
      if (lastIdx < currentIdx) div.classList.add('filled');
      if (groupPhases.indexOf(state.phase) !== -1) div.classList.add('current');
      div.title = seg.label;
      div.style.flex = Math.max(1, groupPhases.length * 0.6) + '';
    }

    bar.appendChild(div);

    var lbl = document.createElement('div');
    lbl.className = 'phase-label';
    var isActive = seg.type === "single" ? seg.phase === state.phase : seg.phases.indexOf(state.phase) !== -1;
    if (isActive) lbl.classList.add('active');
    var labelText = seg.type === "single"
      ? (seg.label.length > 8 ? seg.label.substring(0, 7) + '…' : seg.label)
      : seg.id;
    if (isActive) {
      lbl.innerHTML = labelText + ' <span class="phase-edit-btn" onclick="manualSetPhase()" title="' + t('phase.overrideTitle') + '" style="font-size:1.4rem;cursor:pointer;margin-left:6px;vertical-align:middle;color:var(--accent)">✎</span>';
    } else {
      lbl.textContent = labelText;
    }
    if (seg.gate) lbl.classList.add('phase-gate');
    labels.appendChild(lbl);
  });
}

// ═══════════════════════════════════════════════
//  MANUAL PHASE OVERRIDE
// ═══════════════════════════════════════════════
async function manualSetPhase() {
  var newPhase = prompt(t('dialog.setPhase'), LOCK_DATA.phase || '0');
  if (newPhase === null || newPhase.trim() === '') return;
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  try {
    await apiSetPhase(ctx.projectId, ctx.branch, newPhase.trim());
    await refreshState();
  } catch (err) {
    alert(t('errors.failedToSetPhase', {error: err.message}));
  }
}

// ═══════════════════════════════════════════════
//  APPROVAL STATUS
// ═══════════════════════════════════════════════
function renderApprovalStatus() {
  var container = document.getElementById('approvalStatusPanel');
  if (!container) return;

  function badgeForStatus(status) {
    if (status === 'approved') {
      return '<span class="badge badge-success">' + t('status.approved') + '</span>';
    }
    if (status === 'pending') {
      return '<span class="badge badge-warning">' + t('status.pending') + '</span>';
    }
    return '<span class="badge">' + t('status.notSet') + '</span>';
  }

  var scopeStatus = LOCK_DATA.scope_status || null;
  var planStatus = LOCK_DATA.plan_status || null;

  container.innerHTML =
    '<div style="display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">' +
      '<span style="min-width: 60px; font-size: 0.82rem; font-weight: 600; color: var(--text-secondary);">' + t('phase.scopeStatus') + '</span>' +
      badgeForStatus(scopeStatus) +
      '<button class="btn btn-sm" onclick="switchTab(\'plan\'); setTimeout(function(){ var el = document.querySelector(\'.card:has(#scopeMust)\'); if(el) el.scrollIntoView({behavior:\'smooth\'}); }, 300);">' + t('buttons.viewScope') + '</button>' +
    '</div>' +
    '<div style="display: flex; align-items: center; gap: 12px;">' +
      '<span style="min-width: 60px; font-size: 0.82rem; font-weight: 600; color: var(--text-secondary);">' + t('phase.planStatus') + '</span>' +
      badgeForStatus(planStatus) +
      '<button class="btn btn-sm" onclick="switchTab(\'plan\'); setTimeout(function(){ var el = document.getElementById(\'planContent\'); if(el) el.scrollIntoView({behavior:\'smooth\'}); }, 300);">' + t('buttons.viewPlan') + '</button>' +
    '</div>';
}

// ═══════════════════════════════════════════════
//  PHASE ACTIONS (USER GATES)
// ═══════════════════════════════════════════════
function renderPhaseActions() {
  var container = document.getElementById('phaseActions');
  if (!container) return;
  container.innerHTML = '';

  var phase = state.phase;
  if (!isUserGate(phase)) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.82rem; padding: 8px 0;">' + t('phase.noActionRequired', {phase: phase, name: getPhaseName(phase)}) + '</div>';
    return;
  }

  var div = document.createElement('div');
  div.className = 'phase-action';

  if (phase === "2.1") {
    div.innerHTML = '<div class="phase-action-title">' + t('phaseAction.planReview') + '</div>' +
      '<div class="phase-action-desc">' + t('phaseAction.planReviewDesc') + '</div>' +
      '<textarea id="rejectFeedbackInput" class="ws-input" placeholder="' + t('placeholders.feedbackForChanges') + '" style="margin-top: 8px; min-height: 50px; resize: vertical;"></textarea>' +
      '<div style="display: flex; gap: 8px; margin-top: 8px;">' +
      '<button class="btn btn-primary" onclick="handleApprove()">' + t('buttons.approvePlan') + '</button>' +
      '<button class="btn btn-danger" onclick="handleRejectWithInput()">' + t('buttons.requestChanges') + '</button>' +
      '</div>';
  } else if (/^3\.\d+\.3$/.test(phase)) {
    div.innerHTML = '<div class="phase-action-title">' + t('phaseAction.codeReview', {phase: getPhaseName(phase)}) + '</div>' +
      '<div class="phase-action-desc">' + t('phaseAction.codeReviewDesc') + '</div>' +
      '<input type="text" id="commitMessageInput" class="ws-input" placeholder="' + t('placeholders.commitMessage') + '" style="margin-top: 8px;">' +
      '<textarea id="rejectFeedbackInput" class="ws-input" placeholder="' + t('placeholders.feedbackForChanges') + '" style="margin-top: 6px; min-height: 50px; resize: vertical;"></textarea>' +
      '<div style="display: flex; gap: 8px; margin-top: 8px;">' +
      '<button class="btn btn-primary" onclick="handleApprove()">' + t('buttons.approveChanges') + '</button>' +
      '<button class="btn btn-danger" onclick="handleRejectWithInput()">' + t('buttons.requestChanges') + '</button>' +
      '</div>';
  } else if (phase === "4.2") {
    div.innerHTML = '<div class="phase-action-title">' + t('phaseAction.finalApproval') + '</div>' +
      '<div class="phase-action-desc">' + t('phaseAction.finalApprovalDesc') + '</div>' +
      '<textarea id="rejectFeedbackInput" class="ws-input" placeholder="' + t('placeholders.feedbackForChanges') + '" style="margin-top: 8px; min-height: 50px; resize: vertical;"></textarea>' +
      '<div style="display: flex; gap: 8px; margin-top: 8px;">' +
      '<button class="btn btn-primary" onclick="handleApprove()">' + t('buttons.approveFinish') + '</button>' +
      '<button class="btn btn-danger" onclick="handleRejectWithInput()">' + t('buttons.requestChanges') + '</button>' +
      '</div>';
  }

  container.appendChild(div);
}
