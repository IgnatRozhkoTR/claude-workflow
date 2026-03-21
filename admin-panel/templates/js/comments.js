// ═══════════════════════════════════════════════
//  INLINE COMMENT SYSTEM
// ═══════════════════════════════════════════════
var COMMENTS = AppState.comments;
var SHOW_RESOLVED = false;

function commentKey(scope, target) {
  return scope + ':' + (target || '');
}

function getComments(scope, target) {
  var key = commentKey(scope, target);
  var all = COMMENTS[key] || [];
  if (SHOW_RESOLVED) return all;
  return all.filter(function(c) { return !c.resolved; });
}

function getCommentCount(scope, target) {
  var key = commentKey(scope, target);
  var all = COMMENTS[key] || [];
  return all.filter(function(c) { return !c.resolved; }).length;
}

function getAllCommentCount() {
  var count = 0;
  Object.keys(COMMENTS).forEach(function(key) {
    COMMENTS[key].forEach(function(c) {
      if (!c.resolved) count++;
    });
  });
  return count;
}

function getReviewComments() {
  var result = [];
  Object.keys(COMMENTS).forEach(function(key) {
    if (key.startsWith('review:')) {
      var arr = COMMENTS[key];
      for (var i = 0; i < arr.length; i++) {
        result.push(arr[i]);
      }
    }
  });
  return result;
}

function lineHash(str) {
  var hash = 5381;
  for (var i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) + str.charCodeAt(i);
    hash = hash & hash;
  }
  return (hash >>> 0).toString(16);
}

function addComment(scope, target, text, filePath, lineStart, lineEnd, lHash) {
  if (!text || !text.trim()) return;
  var key = commentKey(scope, target);
  if (!COMMENTS[key]) COMMENTS[key] = [];
  var now = new Date().toISOString();
  var comment = {
    id: null,
    text: text.trim(),
    created_at: now,
    resolved: 0,
    resolved_at: null,
    file_path: filePath || null,
    line_start: lineStart || null,
    line_end: lineEnd || null,
    line_hash: lHash || null
  };
  COMMENTS[key].push(comment);
  var ctx = getWorkspaceContext();
  if (ctx) {
    apiAddComment(ctx.projectId, ctx.branch, scope, target, text, filePath, lineStart, lineEnd, lHash)
      .then(function(res) { if (res.id) comment.id = res.id; })
      .catch(function(e) { console.warn('Failed to persist comment:', e.message); });
  }
}

function toggleResolveComment(scope, target, commentId, currentResolved) {
  var newResolved = currentResolved ? 0 : 1;

  // Update in all COMMENTS keys (comment might be under a different key format)
  var found = false;
  Object.keys(COMMENTS).forEach(function(key) {
    COMMENTS[key].forEach(function(c) {
      if (c.id === commentId) {
        c.resolved = newResolved;
        c.resolved_at = newResolved ? new Date().toISOString() : null;
        found = true;
      }
    });
  });

  if (!found) {
    console.warn('Comment not found in local state:', commentId, 'scope:', scope, 'target:', target);
  }

  var ctx = getWorkspaceContext();
  if (ctx) {
    apiResolveComment(ctx.projectId, ctx.branch, commentId, !!newResolved)
      .catch(function(e) { console.warn('Failed to resolve comment:', e.message); });
  }
}

function formatCommentTime(iso) {
  if (!iso) return '';
  try {
    var d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return iso;
  }
}

function renderCommentIcon(scope, target) {
  var count = getCommentCount(scope, target);
  var hasClass = count > 0 ? ' has-comments' : '';
  var badge = count > 0 ? '<span class="comment-count">' + count + '</span>' : '';
  return '<span class="comment-icon' + hasClass + '" onclick="toggleCommentThread(\'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\', event)" title="' + t('comments.title') + '">' +
    '\u{1F4AC}' + badge + '</span>';
}

function toggleCommentThread(scope, target, event) {
  event.stopPropagation();
  event.preventDefault();

  var icon = event.currentTarget;
  var parent = icon.closest('.plan-task, .scope-item, .finding, .file-item, .file-dir');
  if (!parent) parent = icon.parentElement;

  var existingThread = parent.querySelector('.comment-thread');
  if (existingThread) {
    existingThread.remove();
    return;
  }

  document.querySelectorAll('.comment-thread').forEach(function(el) { el.remove(); });

  var thread = document.createElement('div');
  thread.className = 'comment-thread';
  thread.onclick = function(e) { e.stopPropagation(); };
  thread.innerHTML = renderCommentThread(scope, target);
  parent.appendChild(thread);

  var input = thread.querySelector('.comment-thread-input');
  if (input) input.focus();
}

function renderCommentThread(scope, target) {
  var comments = getComments(scope, target);
  var html = '';

  if (comments.length > 0) {
    html += '<div class="comment-thread-list">';
    comments.forEach(function(c) {
      var resolvedClass = c.resolved ? ' comment-resolved' : '';
      var resolveIcon = c.id ? (
        '<button class="comment-resolve-btn' + (c.resolved ? ' resolved' : '') + '" onclick="onResolveClick(\'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\', ' + c.id + ', ' + c.resolved + ', event)" title="' + (c.resolved ? t('comments.unresolve') : t('buttons.resolve')) + '">' +
        '\u2713' + '</button>'
      ) : '';
      html += '<div class="comment-thread-item' + resolvedClass + '">' +
        resolveIcon +
        '<span class="comment-thread-text">' + escapeHtml(c.text) + '</span>' +
        '<span class="comment-thread-time">' + formatCommentTime(c.created_at) + '</span>' +
        '</div>';
    });
    html += '</div>';
  }

  html += '<div class="comment-thread-form">' +
    '<input type="text" class="comment-thread-input" placeholder="' + t('comments.addComment') + '" ' +
    'onkeydown="handleCommentInput(event, \'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\')">' +
    '<button class="btn btn-sm comment-thread-save" onclick="submitComment(\'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\', this)">' + t('comments.save') + '</button>' +
    '</div>';

  return html;
}

function onResolveClick(scope, target, commentId, currentResolved, event) {
  event.stopPropagation();
  toggleResolveComment(scope, target, commentId, currentResolved);

  var thread = event.target.closest('.comment-thread');
  if (thread) {
    thread.innerHTML = renderCommentThread(scope, target);
  }
}

function handleCommentInput(event, scope, target) {
  if (event.key === 'Enter') {
    event.preventDefault();
    submitComment(scope, target, event.target);
  }
}

function submitComment(scope, target, el) {
  var thread = el.closest('.comment-thread');
  var input = thread.querySelector('.comment-thread-input');
  var text = input.value;
  if (!text || !text.trim()) return;

  var filePath = thread.dataset.filePath || null;
  var lineStart = thread.dataset.lineStart ? parseInt(thread.dataset.lineStart) : null;
  var lineEnd = thread.dataset.lineEnd ? parseInt(thread.dataset.lineEnd) : null;
  var lHash = thread.dataset.lineHash || null;

  addComment(scope, target, text, filePath, lineStart, lineEnd, lHash);
  thread.innerHTML = renderCommentThread(scope, target);

  if (lineStart) {
    renderLineCommentIndicators(scope, target);
  }

  var newInput = thread.querySelector('.comment-thread-input');
  if (newInput) newInput.focus();
}


function escapeAttr(str) {
  return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function escapeHtml(str) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

// ═══════════════════════════════════════════════
//  LINE-BOUND COMMENT HELPERS
// ═══════════════════════════════════════════════

function getLineComments(scope, target, lineNum) {
  var key = commentKey(scope, target);
  var all = COMMENTS[key] || [];
  return all.filter(function(c) {
    if (c.resolved && !SHOW_RESOLVED) return false;
    return c.line_start != null && c.line_start === lineNum;
  });
}

function openLineCommentForm(scope, target, filePath, lineNum, lineContent, containerEl) {
  document.querySelectorAll('.line-comment-form').forEach(function(el) { el.remove(); });
  document.querySelectorAll('.comment-thread[data-line-start]').forEach(function(el) { el.remove(); });

  var existingComments = getLineComments(scope, target, lineNum);
  var lHash = lineHash(lineContent);

  if (existingComments.length > 0) {
    var thread = document.createElement('div');
    thread.className = 'comment-thread';
    thread.dataset.filePath = filePath;
    thread.dataset.lineStart = lineNum;
    thread.dataset.lineEnd = lineNum;
    thread.dataset.lineHash = lHash;
    thread.onclick = function(e) { e.stopPropagation(); };
    thread.innerHTML = renderLineCommentThread(scope, target, lineNum, lHash);
    containerEl.appendChild(thread);
    var input = thread.querySelector('.comment-thread-input');
    if (input) input.focus();
    return;
  }

  var form = document.createElement('div');
  form.className = 'line-comment-form';
  form.onclick = function(e) { e.stopPropagation(); };
  form.innerHTML = '<textarea placeholder="' + t('comments.addCommentOnLine', {line: lineNum}) + '"></textarea>' +
    '<button onclick="submitLineComment(\'' + escapeAttr(scope) + '\', \'' + escapeAttr(target) + '\', \'' + escapeAttr(filePath) + '\', ' + lineNum + ', \'' + escapeAttr(lHash) + '\', this)">' + t('comments.comment') + '</button>';
  containerEl.appendChild(form);
  form.querySelector('textarea').focus();
}

function submitLineComment(scope, target, filePath, lineNum, lHash, btn) {
  var form = btn.closest('.line-comment-form');
  var textarea = form.querySelector('textarea');
  var text = textarea.value;
  if (!text || !text.trim()) return;

  addComment(scope, target, text, filePath, lineNum, lineNum, lHash);
  form.remove();
  renderLineCommentIndicators(scope, target);
}

function renderLineCommentThread(scope, target, lineNum, currentHash) {
  var comments = getLineComments(scope, target, lineNum);
  var html = '';

  if (comments.length > 0) {
    html += '<div class="comment-thread-list">';
    comments.forEach(function(c) {
      var resolvedClass = c.resolved ? ' comment-resolved' : '';
      var resolveIcon = c.id ? (
        '<button class="comment-resolve-btn' + (c.resolved ? ' resolved' : '') + '" onclick="onResolveClick(\'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\', ' + c.id + ', ' + c.resolved + ', event)" title="' + (c.resolved ? t('comments.unresolve') : t('buttons.resolve')) + '">' +
        (c.resolved ? '\u2713' : '\u25CB') + '</button>'
      ) : '';
      var outdatedBadge = '';
      if (c.line_hash && currentHash && c.line_hash !== currentHash) {
        outdatedBadge = '<span class="comment-outdated">' + t('comments.outdated') + '</span>';
      }
      html += '<div class="comment-thread-item' + resolvedClass + '">' +
        resolveIcon +
        '<span class="comment-thread-text">' + escapeHtml(c.text) + outdatedBadge + '</span>' +
        '<span class="comment-thread-time">' + formatCommentTime(c.created_at) + '</span>' +
        '</div>';
    });
    html += '</div>';
  }

  html += '<div class="comment-thread-form">' +
    '<input type="text" class="comment-thread-input" placeholder="' + t('comments.addComment') + '" ' +
    'onkeydown="handleCommentInput(event, \'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\')">' +
    '<button class="btn btn-sm comment-thread-save" onclick="submitComment(\'' + escapeAttr(scope) + '\', \'' + escapeAttr(target || '') + '\', this)">' + t('comments.save') + '</button>' +
    '</div>';

  return html;
}

function renderLineCommentIndicators(scope, target) {
  if (scope === 'review') {
    var diffContainer = document.getElementById('diffContent');
    if (diffContainer && state.selectedFile) {
      diffContainer.querySelectorAll('.line-comment-indicator').forEach(function(el) { el.remove(); });
      diffContainer.querySelectorAll('.line-has-comment, .line-has-unresolved').forEach(function(el) {
        el.classList.remove('line-has-comment', 'line-has-unresolved');
      });
      renderDiffLineCommentIndicators(diffContainer, state.selectedFile);
    }
    renderFileList();
  }
}
