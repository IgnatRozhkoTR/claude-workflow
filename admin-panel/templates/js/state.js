// ═══════════════════════════════════════════════
//  CENTRALIZED APPLICATION STATE
// ═══════════════════════════════════════════════
var AppState = {
  // Server state (populated by applyStateData)
  lock: {
    branch: "",
    phase: "0",
    status: "active",
    scope: {},
    scope_status: "pending",
    plan_status: "pending",
    has_prev_plan: false,
    prev_plan_status: "pending",
    plan: null,
    session_id: null,
    working_dir: null,
    sessions: [],
    locale: null,
    yolo_mode: false
  },
  plan: {
    description: "",
    systemDiagram: "",
    groups: [],
    execution: []
  },
  research: [],
  comments: {},
  context: {
    ticket_id: "",
    ticket_name: "",
    context: "",
    discussions: [],
    refs: []
  },
  diff: {
    files: []
  },
  criteria: [],
  // reviewComments removed: derived from COMMENTS via getReviewComments()
  impactAnalysis: null,
  phaseHistory: [],

  // UI state
  ui: {
    phase: "0",
    diffMode: localStorage.getItem('diff_diffMode') || 'side-by-side',
    fileView: localStorage.getItem('diff_fileView') || 'tree',
    diffSource: localStorage.getItem('diff_diffSource') || 'branch',
    selectedFile: null,
    theme: 'dark'
  }
};

// Backward-compatible aliases so existing consumer code does not need changes
var LOCK_DATA = AppState.lock;
var PLAN_DATA = AppState.plan;
var RESEARCH_DATA = AppState.research;
var DIFF_DATA = AppState.diff;
var state = AppState.ui;

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
  // Lock / session state
  LOCK_DATA.phase = stateData.phase || "0";
  LOCK_DATA.status = stateData.status || "active";
  LOCK_DATA.scope = stateData.scope || {};
  LOCK_DATA.scope_status = stateData.scope_status || "pending";
  LOCK_DATA.plan_status = stateData.plan_status || "pending";
  LOCK_DATA.has_prev_plan = !!stateData.has_prev_plan;
  LOCK_DATA.prev_plan_status = stateData.prev_plan_status || null;
  LOCK_DATA.locale = stateData.locale || null;
  LOCK_DATA.yolo_mode = !!stateData.yolo_mode;

  // Plan — single source is AppState.plan; keep LOCK_DATA.plan as alias
  if (stateData.plan) {
    AppState.plan = stateData.plan;
    PLAN_DATA = AppState.plan;
    LOCK_DATA.plan = AppState.plan;
  } else {
    AppState.plan = { description: "", systemDiagram: "", groups: [], execution: [] };
    PLAN_DATA = AppState.plan;
    LOCK_DATA.plan = null;
  }

  // Research
  if (stateData.research) {
    AppState.research = stateData.research;
    RESEARCH_DATA = AppState.research;
  }

  // Comments — write to AppState, update alias
  AppState.comments = stateData.comments || {};
  COMMENTS = AppState.comments;

  // Impact analysis and phase history — centralized on AppState
  AppState.impactAnalysis = stateData.impact_analysis || null;
  AppState.phaseHistory = (stateData.phaseHistory || []).map(function(h) {
    return { from: h.from, to: h.to, time: h.time };
  });

  // UI state
  state.phase = LOCK_DATA.phase;
}

function resetAppState() {
  // Reset server state
  LOCK_DATA.branch = "";
  LOCK_DATA.phase = "0";
  LOCK_DATA.status = "active";
  LOCK_DATA.scope = {};
  LOCK_DATA.scope_status = "pending";
  LOCK_DATA.plan_status = "pending";
  LOCK_DATA.has_prev_plan = false;
  LOCK_DATA.prev_plan_status = null;
  LOCK_DATA.plan = null;
  LOCK_DATA.session_id = null;
  LOCK_DATA.working_dir = null;
  LOCK_DATA.sessions = [];
  LOCK_DATA.locale = null;
  LOCK_DATA.yolo_mode = false;

  // Reset plan
  PLAN_DATA.description = "";
  PLAN_DATA.systemDiagram = "";
  PLAN_DATA.groups = [];
  PLAN_DATA.execution = [];

  // Reset collections — must mutate in place (aliases point here)
  RESEARCH_DATA.length = 0;
  DIFF_DATA.files = [];
  AppState.comments = {};
  COMMENTS = AppState.comments;
  AppState.context = { ticket_id: "", ticket_name: "", context: "", discussions: [], refs: [] };
  CONTEXT_DATA = AppState.context;
  AppState.criteria = [];
  AppState.impactAnalysis = null;
  AppState.phaseHistory = [];
  window.PHASE_HISTORY = [];
  window.PROVEN_DATA = {};
  window.IMPACT_DATA = null;

  // Reset UI state
  state.phase = "0";
  state.diffSource = localStorage.getItem('diff_diffSource') || 'branch';

  // Dispatch event so components can reset themselves
  document.dispatchEvent(new CustomEvent('workspace-reset'));
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
