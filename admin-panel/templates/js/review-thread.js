// ═══════════════════════════════════════════════
//  REVIEW THREAD COMPONENT
// ═══════════════════════════════════════════════

/**
 * Render a review comment thread (root comment + replies).
 * @param {Object} comment - {id, text, author, file_path, line_start, line_end, created_at, resolved, resolved_at, resolution, replies: [{id, text, author, created_at, status}]}
 * @param {Object} options - {
 *   showFileInfo: boolean,     // show file:line badge (for review tab, not for inline diff)
 *   onResolve: function(id),   // called when resolve/unresolve clicked
 *   onReply: function(id, text), // called when reply submitted
 *   onFileClick: function(file_path, line_start, line_end), // called when file badge clicked
 * }
 * @returns {HTMLElement} - the thread DOM element
 */
function renderReviewThread(comment, options) {
  var opts = options || {};

  var thread = document.createElement('div');
  thread.className = 'review-thread' + (comment.resolved ? ' review-thread-resolved' : '');

  thread.appendChild(buildReviewThreadHeader(comment, opts));
  thread.appendChild(buildReviewThreadText(comment));
  thread.appendChild(buildReviewThreadReplies(comment));
  thread.appendChild(buildReviewReplyForm(comment, opts));

  return thread;
}

function buildReviewThreadHeader(comment, opts) {
  var header = document.createElement('div');
  header.className = 'review-thread-header';

  var author = comment.author || 'user';
  var authorBadge = document.createElement('span');
  authorBadge.className = 'review-author review-author-' + author;
  authorBadge.textContent = t('author.' + author);
  header.appendChild(authorBadge);

  if (opts.showFileInfo && comment.file_path) {
    var fileBadge = buildReviewFileBadge(comment, opts);
    header.appendChild(fileBadge);
  }

  if (comment.resolution && comment.resolution !== 'open') {
    var resBadge = document.createElement('span');
    resBadge.className = 'review-resolution review-resolution-' + comment.resolution;
    resBadge.textContent = t('review.resolution.' + comment.resolution);
    header.appendChild(resBadge);
  }

  var resolveBtn = buildReviewResolveButton(comment, opts);
  header.appendChild(resolveBtn);

  return header;
}

function buildReviewFileBadge(comment, opts) {
  var badge = document.createElement('span');
  badge.className = 'review-file-badge';

  var label = comment.file_path;
  if (comment.line_start) {
    label += ':' + comment.line_start;
    if (comment.line_end && comment.line_end !== comment.line_start) {
      label += '-' + comment.line_end;
    }
  }
  badge.textContent = label;

  if (typeof opts.onFileClick === 'function') {
    badge.addEventListener('click', function() {
      opts.onFileClick(comment.file_path, comment.line_start, comment.line_end);
    });
  }

  return badge;
}

function buildReviewResolveButton(comment, opts) {
  var btn = document.createElement('button');
  btn.className = 'review-resolve-btn';
  btn.textContent = comment.resolved ? t('comments.unresolve') : t('buttons.resolve');

  if (typeof opts.onResolve === 'function') {
    btn.addEventListener('click', function() {
      opts.onResolve(comment.id);
    });
  }

  return btn;
}

function buildReviewThreadText(comment) {
  var textEl = document.createElement('div');
  textEl.className = 'review-thread-text';
  textEl.textContent = comment.text;
  return textEl;
}

function buildReviewThreadReplies(comment) {
  var repliesEl = document.createElement('div');
  repliesEl.className = 'review-thread-replies';

  var replies = comment.replies || [];
  replies.forEach(function(reply) {
    repliesEl.appendChild(buildReviewReply(reply));
  });

  return repliesEl;
}

function buildReviewReply(reply) {
  var replyEl = document.createElement('div');
  replyEl.className = 'review-reply';

  var meta = document.createElement('div');
  meta.className = 'review-reply-meta';

  var author = reply.author || 'user';
  var authorBadge = document.createElement('span');
  authorBadge.className = 'review-author review-author-' + author;
  authorBadge.textContent = t('author.' + author);
  meta.appendChild(authorBadge);

  if (reply.created_at) {
    var timeSpan = document.createElement('span');
    timeSpan.style.marginLeft = '6px';
    timeSpan.textContent = formatRelativeDate(reply.created_at);
    meta.appendChild(timeSpan);
  }

  replyEl.appendChild(meta);

  var textEl = document.createElement('div');
  textEl.className = 'review-reply-text';
  textEl.textContent = reply.text;
  replyEl.appendChild(textEl);

  return replyEl;
}

function buildReviewReplyForm(comment, opts) {
  var form = document.createElement('div');
  form.className = 'review-reply-form';

  var input = document.createElement('input');
  input.type = 'text';
  input.className = 'review-reply-input';
  input.placeholder = t('placeholders.replyDots');

  var btn = document.createElement('button');
  btn.className = 'review-reply-btn';
  btn.textContent = t('buttons.reply');

  function submitReply() {
    var text = input.value.trim();
    if (!text) return;
    if (typeof opts.onReply === 'function') {
      opts.onReply(comment.id, text);
    }
    input.value = '';
  }

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitReply();
    }
  });

  btn.addEventListener('click', submitReply);

  form.appendChild(input);
  form.appendChild(btn);

  return form;
}
