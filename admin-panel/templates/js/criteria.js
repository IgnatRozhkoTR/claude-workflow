// ═══════════════════════════════════════════════
//  ACCEPTANCE CRITERIA
// ═══════════════════════════════════════════════
var CRITERIA_DATA = [];

function loadCriteria() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/criteria')
    .then(function(data) {
      if (data && data.criteria) {
        CRITERIA_DATA = data.criteria;
        renderCriteria();
      }
    });
}

function renderCriteria() {
  var list = document.getElementById('criteriaList');
  if (!list) return;

  if (CRITERIA_DATA.length === 0) {
    list.innerHTML = '<p style="color: var(--text-secondary); font-size: 13px;">' + t('criteria.noEntries') + '</p>';
    return;
  }

  list.innerHTML = CRITERIA_DATA.map(function(c) {
    var statusBadge = '';
    if (c.status === 'proposed') {
      var sourceLabel = c.source === 'agent' ? t('badges.proposedByAgent') : t('badges.pendingReview');
      statusBadge = '<span class="badge badge-warning">' + sourceLabel + '</span>' +
        ' <button class="btn btn-sm" onclick="updateCriterionStatus(' + c.id + ', \'accepted\')">' + t('buttons.accept') + '</button>' +
        ' <button class="btn btn-sm btn-danger" onclick="updateCriterionStatus(' + c.id + ', \'rejected\')">' + t('buttons.deny') + '</button>';
    } else if (c.status === 'accepted') {
      statusBadge = '<span class="badge badge-success">' + t('badges.accepted') + '</span>';
    } else if (c.status === 'rejected') {
      statusBadge = '<span class="badge badge-danger">' + t('badges.rejected') + '</span>';
    }

    var validationBadge = '';
    if (c.validated === 1) {
      validationBadge = ' <span class="badge badge-success" title="' + escapeHtml(c.validation_message || '') + '">' + t('badges.passed') + '</span>';
    } else if (c.validated === -1) {
      validationBadge = ' <span class="badge badge-danger" title="' + escapeHtml(c.validation_message || '') + '">' + t('badges.failed') + '</span>';
    }

    if (c.type === 'custom') {
      if (c.validated === 1) {
        validationBadge = ' <span class="badge badge-success">' + t('badges.userApproved') + '</span>';
      } else if (c.validated === -1) {
        validationBadge = ' <span class="badge badge-danger">' + t('badges.userRejected') + '</span>' +
          ' <button class="btn btn-sm" onclick="validateCriterion(' + c.id + ', true)">' + t('buttons.reapprove') + '</button>';
      }
    }

    var typeKeyMap = { unit_test: 'criteria.unitTest', integration_test: 'criteria.integrationTest', bdd_scenario: 'criteria.bddScenario', custom: 'criteria.custom' };
    var typeLabel = t(typeKeyMap[c.type] || 'criteria.' + c.type);
    var hasDetails = c.details && (c.details.file || c.details.test_names || c.details.scenario_names || c.details.instruction);
    var detailsHint = hasDetails ? ' <span style="color: var(--accent); cursor: pointer; font-size: 12px;" title="' + t('criteria.viewDetails') + '">&#9658; ' + t('criteria.detailsLink') + '</span>' : '';
    var descClick = hasDetails ? ' onclick="showCriterionDetails(' + c.id + '); event.stopPropagation();" style="cursor: pointer;"' : '';

    var criterionComments = '';
    if (typeof COMMENTS !== 'undefined') {
      var key = 'criteria';
      var items = COMMENTS[key] || [];
      var matching = items.filter(function(cmt) { return cmt.target === 'criterion:' + c.id && !cmt.resolved; });
      if (matching.length > 0) {
        criterionComments = '<div style="margin-top: 4px; padding: 4px 8px; background: var(--bg-tertiary); border-radius: 4px; font-size: 12px;">' +
          matching.map(function(cmt) {
            return '<div style="color: var(--text-secondary); margin: 2px 0;">💬 ' + escapeHtml(cmt.text) + '</div>';
          }).join('') +
        '</div>';
      }
    }

    return '<div class="criteria-item" style="padding: 8px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 6px;">' +
      '<div style="display: flex; justify-content: space-between; align-items: center;">' +
        '<div' + descClick + '>' +
          '<span style="font-weight: 500; text-transform: capitalize;">' + typeLabel + '</span>' +
          '<span style="margin-left: 8px; color: var(--text-secondary);">' + escapeHtml(c.description) + detailsHint + '</span>' +
        '</div>' +
        '<div style="display: flex; align-items: center; gap: 6px;">' +
          statusBadge + validationBadge +
          ' <button class="btn btn-sm btn-danger" onclick="deleteCriterion(' + c.id + ')" title="' + t('buttons.delete') + '">&times;</button>' +
        '</div>' +
      '</div>' +
      criterionComments +
    '</div>';
  }).join('');
}

function showCriterionDetails(id) {
  var c = CRITERIA_DATA.find(function(item) { return item.id === id; });
  if (!c || !c.details) return;

  var modal = document.getElementById('criterionDetailModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'criterionDetailModal';
    modal.className = 'file-preview-modal';
    modal.onclick = function(e) { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = '<div class="file-preview-content" style="max-width: 600px;">' +
      '<div class="file-preview-header">' +
        '<span class="file-preview-path" id="criterionDetailTitle"></span>' +
        '<button class="file-preview-close" onclick="document.getElementById(\'criterionDetailModal\').classList.remove(\'open\')">&times;</button>' +
      '</div>' +
      '<div class="file-preview-body" style="padding: 16px;" id="criterionDetailBody"></div>' +
    '</div>';
    document.body.appendChild(modal);
  }

  var typeKeyMap = { unit_test: 'criteria.unitTest', integration_test: 'criteria.integrationTest', bdd_scenario: 'criteria.bddScenario', custom: 'criteria.custom' };
  var typeLabel = t(typeKeyMap[c.type] || 'criteria.' + c.type);
  document.getElementById('criterionDetailTitle').textContent = typeLabel + ': ' + c.description;

  var html = '';
  var d = c.details;

  if (d.file) {
    html += '<div style="margin-bottom: 12px;">' +
      '<div style="font-weight: 500; margin-bottom: 4px;">' + t('labels.file') + '</div>' +
      '<code style="font-size: 13px;">' + escapeHtml(d.file) + '</code>' +
    '</div>';
  }

  var names = d.test_names || d.scenario_names || [];
  if (names.length > 0) {
    var label = d.test_names ? t('labels.testMethods') : t('labels.scenarios');
    html += '<div style="margin-bottom: 12px;">' +
      '<div style="font-weight: 500; margin-bottom: 4px;">' + label + ' (' + names.length + ')</div>' +
      '<ul style="margin: 0; padding-left: 20px; font-size: 13px;">' +
      names.map(function(n) { return '<li><code>' + escapeHtml(n) + '</code></li>'; }).join('') +
      '</ul>' +
    '</div>';
  }

  if (d.instruction) {
    html += '<div style="margin-bottom: 12px;">' +
      '<div style="font-weight: 500; margin-bottom: 4px;">' + t('labels.instruction') + '</div>' +
      '<div style="font-size: 13px; color: var(--text-secondary);">' + escapeHtml(d.instruction) + '</div>' +
    '</div>';
  }

  if (c.validation_message) {
    var color = c.validated === 1 ? 'var(--success)' : c.validated === -1 ? 'var(--danger)' : 'var(--text-secondary)';
    html += '<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);">' +
      '<div style="font-weight: 500; margin-bottom: 4px;">' + t('labels.validationResult') + '</div>' +
      '<div style="font-size: 13px; color: ' + color + ';">' + escapeHtml(c.validation_message) + '</div>' +
    '</div>';
  }

  if (!html) html = '<div style="color: var(--text-secondary);">' + t('criteria.noDetailsAvailable') + '</div>';

  document.getElementById('criterionDetailBody').innerHTML = html;
  modal.classList.add('open');
}

function addCriterion() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var type = document.getElementById('criteriaType').value;
  var desc = document.getElementById('criteriaDesc').value.trim();
  if (!desc) return;

  var body = { type: type, description: desc };

  if (type !== 'custom') {
    var file = document.getElementById('criteriaFile').value.trim();
    var namesStr = document.getElementById('criteriaTestNames').value.trim();
    var details = {};
    if (file) details.file = file;
    if (namesStr) {
      var nameKey = type === 'bdd_scenario' ? 'scenario_names' : 'test_names';
      details[nameKey] = namesStr.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    }
    if (Object.keys(details).length > 0) {
      body.details_json = JSON.stringify(details);
    }
  } else {
    var customDesc = document.getElementById('criteriaDesc').value.trim();
    if (customDesc) {
      body.details_json = JSON.stringify({ instruction: customDesc });
    }
  }

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/criteria', body)
    .then(function() {
      document.getElementById('criteriaDesc').value = '';
      document.getElementById('criteriaFile').value = '';
      document.getElementById('criteriaTestNames').value = '';
      loadCriteria();
    });
}

function updateCriterionStatus(id, status) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  if (status === 'rejected') {
    var reason = prompt(t('criteria.rejectReason'));
    var base = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch);
    apiPut(base + '/criteria/' + id, { status: status })
      .then(function() {
        if (reason && reason.trim()) {
          return apiPost(base + '/comments', {
            scope: 'criteria',
            target: 'criterion:' + id,
            text: reason.trim()
          });
        }
      })
      .then(function() { loadCriteria(); });
  } else {
    apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/criteria/' + id, { status: status })
      .then(function() { loadCriteria(); });
  }
}

function deleteCriterion(id) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  apiDelete('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/criteria/' + id)
    .then(function() { loadCriteria(); });
}

async function validateCriterion(id, passed) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  await apiPut('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/criteria/' + id + '/validate', { passed: passed });
  await loadCriteria();
}

document.addEventListener('DOMContentLoaded', function() {
  var typeSelect = document.getElementById('criteriaType');
  if (typeSelect) {
    var detailsForm = document.getElementById('criteriaDetailsForm');
    // Show details for initial value (unit_test)
    if (detailsForm && typeSelect.value !== 'custom') {
      detailsForm.style.display = 'block';
    }
    typeSelect.addEventListener('change', function() {
      if (detailsForm) {
        detailsForm.style.display = this.value !== 'custom' ? 'block' : 'none';
      }
    });
  }
});

EventBus.on('state:refreshed', function() {
  if (typeof loadCriteria === 'function') loadCriteria();
});
