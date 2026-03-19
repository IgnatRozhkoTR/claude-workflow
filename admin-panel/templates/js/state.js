// ═══════════════════════════════════════════════
//  WORKSPACE DATA
// ═══════════════════════════════════════════════
let LOCK_DATA = {
  branch: "",
  phase: "0",
  status: "active",
  scope: {},
  scope_status: "pending",
  plan_status: "pending",
  plan: null,
  session_id: null,
  working_dir: null,
  locale: null
};

let PLAN_DATA = {
  description: "",
  systemDiagram: "",
  groups: [],
  execution: []
};

let RESEARCH_DATA = [];

let DIFF_DATA = {
  files: []
};

// ═══════════════════════════════════════════════
//  STATE
// ═══════════════════════════════════════════════
let state = {
  phase: "0",
  diffMode: localStorage.getItem('diff_diffMode') || 'side-by-side',
  fileView: localStorage.getItem('diff_fileView') || 'tree',
  diffSource: localStorage.getItem('diff_diffSource') || 'branch',
  selectedFile: null,
  theme: 'dark'
};

const PHASE_NAMES = {
  "0": "phase.init",
  "1.0": "phase.assessment",
  "1.1": "phase.research",
  "1.2": "phase.proving",
  "1.3": "phase.impactAnalysis",
  "1.4": "phase.preplanningReview",
  "2.0": "phase.planning",
  "2.1": "phase.planReview",
  "4.0": "phase.agenticReview",
  "4.1": "phase.addressFix",
  "4.2": "phase.finalApproval",
  "5": "phase.done"
};

function getPhaseName(phase) {
  if (PHASE_NAMES[phase]) return t(PHASE_NAMES[phase]);
  if (phase === '3.N') return t('phase.execution') || 'Execution';
  var match = phase.match(/^3\.(\d+)\.(\d+)$/);
  if (match) {
    var n = match[1];
    var k = match[2];
    var subNameKeys = ["phase.implementation", "phase.validation", "phase.fixes", "phase.codeReview", "phase.commit"];
    var plan = PLAN_DATA || {};
    var execution = plan.execution || [];
    var subPhase = execution.find(function(e) { return e.id === "3." + n; });
    var groupName = subPhase ? subPhase.name : t('phase.subPhase', {n: n});
    var stepKey = subNameKeys[parseInt(k)];
    return t('phase.subPhaseName', {groupName: groupName, step: stepKey ? t(stepKey) : t('phase.step', {n: k})});
  }
  return t('phase.phaseName', {phase: phase});
}

const USER_GATES = new Set(["1.4", "2.1", "4.2"]);

function isUserGate(phase) {
  if (USER_GATES.has(phase)) return true;
  return /^3\.\d+\.3$/.test(phase);
}

// ═══════════════════════════════════════════════
//  SHARED UTILITIES
// ═══════════════════════════════════════════════

function applyStateData(stateData) {
  LOCK_DATA.phase = stateData.phase || "0";
  LOCK_DATA.status = stateData.status || "active";
  LOCK_DATA.scope = stateData.scope || {};
  LOCK_DATA.scope_status = stateData.scope_status || "pending";
  LOCK_DATA.plan_status = stateData.plan_status || "pending";
  LOCK_DATA.has_prev_plan = !!stateData.has_prev_plan;
  LOCK_DATA.prev_plan_status = stateData.prev_plan_status || null;
  LOCK_DATA.locale = stateData.locale || null;

  if (stateData.plan) {
    PLAN_DATA = stateData.plan;
    LOCK_DATA.plan = stateData.plan;
  } else {
    LOCK_DATA.plan = null;
  }
  if (stateData.research) RESEARCH_DATA = stateData.research;
  window.PROVEN_DATA = stateData.proven || {};

  COMMENTS = stateData.comments || {};

  state.phase = LOCK_DATA.phase;
  window.PHASE_HISTORY = (stateData.phaseHistory || []).map(function(h) {
    return { from: h.from, to: h.to, time: h.time };
  });
}

function copyToClipboard(text, successMessage) {
  navigator.clipboard.writeText(text).then(function() {
    showToast(successMessage);
  });
}

function formatRelativeDate(isoString) {
  var date = new Date(isoString);
  var now = new Date();
  var diffMs = now - date;
  var diffMin = Math.floor(diffMs / 60000);
  var diffHour = Math.floor(diffMin / 60);
  var diffDay = Math.floor(diffHour / 24);
  if (diffMin < 1) return t('time.justNow');
  if (diffMin < 60) return t('time.minAgo', {n: diffMin});
  if (diffHour < 24) return diffHour === 1 ? t('time.hourAgo', {n: diffHour}) : t('time.hoursAgo', {n: diffHour});
  if (diffDay < 7) return diffDay === 1 ? t('time.dayAgo', {n: diffDay}) : t('time.daysAgo', {n: diffDay});
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function makeResizable(handleId, panelId) {
  var handle = document.getElementById(handleId);
  var panel = document.getElementById(panelId);
  if (!handle || !panel) return;

  var dragging = false;
  var startX, startWidth;

  handle.addEventListener('mousedown', function(e) {
    dragging = true;
    startX = e.clientX;
    startWidth = panel.offsetWidth;
    handle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!dragging) return;
    var newWidth = startWidth + (e.clientX - startX);
    newWidth = Math.max(140, Math.min(newWidth, window.innerWidth * 0.5));
    panel.style.width = newWidth + 'px';
  });

  document.addEventListener('mouseup', function() {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
}
