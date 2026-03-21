// ═══════════════════════════════════════════════
//  REVIEW TAB
// ═══════════════════════════════════════════════

async function loadReviewComments() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    try {
        var data = await apiListComments(ctx.projectId, ctx.branch, 'review');
        var comments = data.comments || [];

        Object.keys(COMMENTS).forEach(function(key) {
            if (key.startsWith('review:')) delete COMMENTS[key];
        });
        comments.forEach(function(c) {
            var key = 'review:' + c.file_path;
            if (!COMMENTS[key]) COMMENTS[key] = [];
            COMMENTS[key].push(c);
        });

        renderReviewTab();
        updateReviewBadge();
    } catch(e) {
        console.warn('Failed to load review comments:', e.message);
    }
}

function renderReviewTab() {
    var container = document.getElementById('reviewCommentsList');
    if (!container) return;
    container.innerHTML = '';

    var allReview = getReviewComments();
    var showResolved = container.dataset.showResolved === 'true';
    var filtered = showResolved ? allReview : allReview.filter(function(c) { return !c.resolved; });
    var roots = filtered.filter(function(c) { return !c.parent_id; });

    if (roots.length === 0) {
        container.innerHTML = '<div class="no-items-msg">' + t('review.noComments') + '</div>';
        return;
    }

    roots.forEach(function(comment) {
        var thread = renderReviewThread(comment, {
            showFileInfo: true,
            onResolve: function(id) { resolveReviewTabComment(id); },
            onReply: function(id, text) { replyToReviewTabComment(id, text); },
            onFileClick: function(filePath, lineStart, lineEnd) {
                openFileViewer(filePath, lineStart, lineEnd);
            }
        });
        container.appendChild(thread);
    });
}

async function resolveReviewTabComment(commentId) {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    try {
        var allReview = getReviewComments();
        var comment = allReview.find(function(c) { return c.id === commentId; });
        var resolved = comment && comment.resolved;
        await apiResolveComment(ctx.projectId, ctx.branch, commentId, !resolved);
        await loadReviewComments();
        renderDiffView();
    } catch(e) {
        showToast(t('messages.failedToResolve', {error: e.message}));
    }
}

async function replyToReviewTabComment(commentId, text) {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    try {
        await apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/comments/' + commentId + '/reply', {text: text});
        await loadReviewComments();
        renderDiffView();
    } catch(e) {
        showToast(t('messages.failedToUpdate', {error: e.message}));
    }
}

function openFileViewer(filePath, lineStart, lineEnd) {
    if (typeof showFilePreview === 'function') {
        showFilePreview(filePath, lineStart, lineEnd);
    }
}

function updateReviewBadge() {
    var badge = document.getElementById('reviewBadge');
    if (!badge) return;
    var allReview = getReviewComments();
    var unresolved = allReview.filter(function(c) { return !c.parent_id && !c.resolved; }).length;
    if (unresolved > 0) {
        badge.textContent = unresolved;
        badge.style.display = 'inline-flex';
    } else {
        badge.style.display = 'none';
    }
}

function toggleReviewResolved() {
    var container = document.getElementById('reviewCommentsList');
    var btn = document.getElementById('reviewShowResolvedBtn');
    if (!container || !btn) return;
    var showing = container.dataset.showResolved === 'true';
    container.dataset.showResolved = showing ? 'false' : 'true';
    btn.textContent = showing ? t('review.showResolved') : t('review.hideResolved');
    renderReviewTab();
}
