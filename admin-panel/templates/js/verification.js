// ═══════════════════════════════════════════════
//  VERIFICATION PROFILES
// ═══════════════════════════════════════════════

var VERIFICATION_PROFILES = [];
var WORKSPACE_VERIFICATION = [];
var VERIFICATION_RESULTS = null;

async function loadVerificationData() {
    var ctx = getWorkspaceContext();
    try {
        var resp = await fetch('/api/verification/profiles');
        var allProfiles = await resp.json();
        VERIFICATION_PROFILES = allProfiles.profiles || [];
    } catch(e) {
        console.warn('Failed to load verification profiles:', e.message);
    }

    if (ctx) {
        try {
            var wsProfiles = await apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/verification/profiles');
            WORKSPACE_VERIFICATION = wsProfiles.profiles || [];
        } catch(e) {
            console.warn('Failed to load workspace verification profiles:', e.message);
            WORKSPACE_VERIFICATION = [];
        }
    }

    renderVerification();
}

async function loadVerificationResults() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    try {
        var results = await apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/verification/results');
        VERIFICATION_RESULTS = results.steps ? results : null;
        renderVerificationResults();
    } catch(e) {
        console.warn('Failed to load verification results:', e.message);
    }
}

function renderVerification() {
    renderAssignedProfiles();
    renderProfileSelector();
}

function renderAssignedProfiles() {
    var container = document.getElementById('verificationAssigned');
    if (!container) return;
    container.innerHTML = '';

    if (WORKSPACE_VERIFICATION.length === 0) {
        container.innerHTML = '<div class="no-items-msg">' + t('verification.noProfiles') + '</div>';
        return;
    }

    WORKSPACE_VERIFICATION.forEach(function(profile) {
        var el = document.createElement('div');
        el.className = 'verification-profile-card';

        var stepsHtml = (profile.steps || []).map(function(step) {
            var statusClass = step.enabled ? 'step-enabled' : 'step-disabled';
            var severityBadge = step.fail_severity === 'blocking'
                ? '<span class="severity-badge severity-blocking">blocking</span>'
                : '<span class="severity-badge severity-warning">warning</span>';
            return '<div class="verification-step ' + statusClass + '">'
                + '<label class="step-toggle">'
                + '<input type="checkbox" ' + (step.enabled ? 'checked' : '') + ' onchange="toggleVerificationStep(' + step.id + ', this.checked)">'
                + '<span class="step-name">' + escapeHtml(step.name) + '</span>'
                + '</label>'
                + severityBadge
                + '<code class="step-command">' + escapeHtml(step.command) + '</code>'
                + '</div>';
        }).join('');

        var subpathNote = profile.subpath !== '.' ? ' <span class="subpath-badge">' + escapeHtml(profile.subpath) + '</span>' : '';

        el.innerHTML = '<div class="verification-profile-header">'
            + '<span class="verification-profile-name">' + escapeHtml(profile.name) + subpathNote + '</span>'
            + '<button class="btn btn-sm btn-outline" onclick="unassignVerificationProfile(' + profile.assignment_id + ')">' + t('verification.remove') + '</button>'
            + '</div>'
            + '<div class="verification-steps">' + stepsHtml + '</div>';

        container.appendChild(el);
    });
}

function renderProfileSelector() {
    var select = document.getElementById('verificationProfileSelect');
    if (!select) return;

    var assignedIds = WORKSPACE_VERIFICATION.map(function(p) { return p.id; });
    var available = VERIFICATION_PROFILES.filter(function(p) { return assignedIds.indexOf(p.id) === -1; });

    select.innerHTML = '<option value="">' + t('verification.selectProfile') + '</option>';
    available.forEach(function(p) {
        var opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name + ' (' + p.language + ')';
        select.appendChild(opt);
    });
}

function renderVerificationResults() {
    var container = document.getElementById('verificationResults');
    if (!container) return;

    if (!VERIFICATION_RESULTS || !VERIFICATION_RESULTS.steps) {
        container.innerHTML = '<div class="no-items-msg">' + t('verification.noRuns') + '</div>';
        return;
    }

    var run = VERIFICATION_RESULTS;
    var statusClass = 'run-' + run.status;

    var stepsHtml = (run.steps || []).map(function(step) {
        var stepClass = 'result-' + step.status;
        var outputHtml = step.output ? '<pre class="step-output">' + escapeHtml(step.output) + '</pre>' : '';
        var durationStr = step.duration_ms ? ' (' + (step.duration_ms / 1000).toFixed(1) + 's)' : '';
        return '<div class="verification-result-step ' + stepClass + '">'
            + '<div class="result-step-header">'
            + '<span class="result-step-status">' + step.status.toUpperCase() + '</span>'
            + '<span class="result-step-name">' + escapeHtml(step.profile_name) + ' / ' + escapeHtml(step.step_name) + durationStr + '</span>'
            + '</div>'
            + outputHtml
            + '</div>';
    }).join('');

    container.innerHTML = '<div class="verification-run ' + statusClass + '">'
        + '<div class="run-header">'
        + '<span class="run-status-badge">' + run.status.toUpperCase() + '</span>'
        + '<span class="run-phase">Phase ' + escapeHtml(run.phase) + '</span>'
        + '<span class="run-time">' + (run.completed_at || run.started_at) + '</span>'
        + '</div>'
        + stepsHtml
        + '</div>';
}

async function assignVerificationProfile() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    var select = document.getElementById('verificationProfileSelect');
    var subpathInput = document.getElementById('verificationSubpath');
    var profileId = select ? parseInt(select.value) : 0;
    if (!profileId) return;
    var subpath = subpathInput ? subpathInput.value.trim() || '.' : '.';

    try {
        await apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/verification/assign', {
            profile_id: profileId,
            subpath: subpath
        });
        if (subpathInput) subpathInput.value = '';
        await loadVerificationData();
    } catch(e) {
        if (typeof showToast === 'function') showToast('Failed to assign: ' + e.message);
    }
}

async function unassignVerificationProfile(assignmentId) {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    try {
        await fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/verification/unassign/' + assignmentId, {method: 'DELETE'});
        await loadVerificationData();
    } catch(e) {
        if (typeof showToast === 'function') showToast('Failed to remove: ' + e.message);
    }
}

async function toggleVerificationStep(stepId, enabled) {
    try {
        await fetch('/api/verification/steps/' + stepId, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: enabled})
        });
        await loadVerificationData();
    } catch(e) {
        if (typeof showToast === 'function') showToast('Failed to update step: ' + e.message);
        await loadVerificationData();
    }
}

async function runVerificationManual() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    var btn = document.getElementById('runVerificationBtn');
    if (btn) { btn.disabled = true; btn.textContent = t('verification.running'); }
    try {
        var resp = await apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/verification/run', {});
        VERIFICATION_RESULTS = resp.steps ? resp : null;
        renderVerificationResults();
        if (typeof showToast === 'function') {
            var status = resp.status || resp.message || 'done';
            showToast(status === 'passed' ? t('verification.runPassed') : status === 'failed' ? t('verification.runFailed') : status);
        }
    } catch(e) {
        if (typeof showToast === 'function') showToast(t('verification.runError') + ': ' + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = t('verification.run'); }
    }
}
