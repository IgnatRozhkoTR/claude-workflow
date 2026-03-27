// ═══════════════════════════════════════════════
//  IMPROVEMENTS
// ═══════════════════════════════════════════════

var IMPROVEMENTS = [];

async function loadImprovements() {
    try {
        var scopeFilter = document.getElementById('improvementScopeFilter');
        var statusFilter = document.getElementById('improvementStatusFilter');
        var params = new URLSearchParams();
        if (scopeFilter && scopeFilter.value) params.set('scope', scopeFilter.value);
        if (statusFilter && statusFilter.value) params.set('status', statusFilter.value);
        var url = '/api/improvements' + (params.toString() ? '?' + params.toString() : '');
        var resp = await fetch(url);
        var data = await resp.json();
        IMPROVEMENTS = data.improvements || [];
        renderImprovements();
    } catch(e) {
        console.warn('Failed to load improvements:', e.message);
    }
}

function renderImprovements() {
    var container = document.getElementById('improvementsList');
    if (!container) return;
    container.innerHTML = '';

    if (IMPROVEMENTS.length === 0) {
        container.innerHTML = '<div class="no-items-msg">' + t('improvements.noItems') + '</div>';
        return;
    }

    IMPROVEMENTS.forEach(function(item) {
        var el = document.createElement('div');
        el.className = 'improvement-item' + (item.status === 'resolved' ? ' resolved' : '');

        var scopeClass = 'improvement-scope scope-' + item.scope;

        var html = '<div class="improvement-header">'
            + '<span class="' + scopeClass + '">' + escapeHtml(item.scope) + '</span>'
            + '<span class="improvement-title">' + escapeHtml(item.title) + '</span>'
            + '<span class="improvement-date">' + formatDate(item.created_at) + '</span>'
            + '</div>'
            + '<div class="improvement-body">' + escapeHtml(item.description) + '</div>';

        if (item.context) {
            html += '<div class="improvement-context">' + escapeHtml(item.context) + '</div>';
        }

        if (item.status === 'resolved' && item.resolved_note) {
            html += '<div class="improvement-resolved-note"><strong>' + t('improvements.resolvedNote') + ':</strong> ' + escapeHtml(item.resolved_note) + '</div>';
        }

        html += '<div class="improvement-actions">';
        if (item.status === 'open') {
            html += '<button class="btn btn-sm" onclick="resolveImprovement(' + item.id + ')">' + t('improvements.resolve') + '</button>';
        } else {
            html += '<button class="btn btn-sm btn-outline" onclick="reopenImprovement(' + item.id + ')">' + t('improvements.reopen') + '</button>';
        }
        html += '</div>';

        el.innerHTML = html;
        container.appendChild(el);
    });
}

async function resolveImprovement(id) {
    var note = prompt(t('improvements.resolvePrompt'));
    if (note === null) return;
    try {
        await fetch('/api/improvements/' + id + '/resolve', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({note: note})
        });
        await loadImprovements();
        updateImprovementBadge();
    } catch(e) {
        if (typeof showToast === 'function') showToast('Failed to resolve: ' + e.message);
    }
}

async function reopenImprovement(id) {
    try {
        await fetch('/api/improvements/' + id + '/reopen', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'}
        });
        await loadImprovements();
        updateImprovementBadge();
    } catch(e) {
        if (typeof showToast === 'function') showToast('Failed to reopen: ' + e.message);
    }
}

function formatDate(isoStr) {
    if (!isoStr) return '';
    var d = new Date(isoStr);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

async function updateImprovementBadge() {
    var badge = document.getElementById('improvementBadge');
    if (!badge) return;
    try {
        var resp = await fetch('/api/improvements?status=open');
        var data = await resp.json();
        var count = (data.improvements || []).length;
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    } catch(e) {
        badge.style.display = 'none';
    }
}
