// ═══════════════════════════════════════════════
//  DIFF FILE LIST
// ═══════════════════════════════════════════════
var _diffFilter = '';
var _showResolved = false;

function filterDiffFiles(query) {
  _diffFilter = query.toLowerCase();
  renderFileList();
}

function buildFileTree(files) {
  const tree = {};
  files.forEach(f => {
    const parts = f.path.split('/');
    let node = tree;
    parts.forEach((part, i) => {
      if (i === parts.length - 1) {
        node[part] = f;
      } else {
        if (!node[part] || typeof node[part] !== 'object' || node[part].path) node[part] = {};
        node = node[part];
      }
    });
  });
  return tree;
}

function fileHasUnresolvedComments(filePath) {
  var key = 'review:' + filePath;
  var all = COMMENTS[key] || [];
  return all.some(function(c) { return !c.resolved && !c.parent_id; });
}

function renderFileList() {
  const container = document.getElementById('diffFileList');
  const header = container.querySelector('.diff-file-list-header');
  container.innerHTML = '';
  container.appendChild(header);

  var files = DIFF_DATA.files;
  if (_diffFilter) {
    files = files.filter(function(f) { return f.path.split('/').pop().toLowerCase().indexOf(_diffFilter) !== -1; });
  }

  if (state.fileView === 'flat') {
    files.forEach(f => {
      const div = document.createElement('div');
      div.className = 'file-item' + (state.selectedFile === f.path ? ' active' : '');
      div.title = f.path;
      div.onclick = (e) => { if (!e.target.closest('.comment-icon')) selectFile(f.path); };
      var unresolvedDot = fileHasUnresolvedComments(f.path) ? '<span class="file-unresolved-dot" title="Has unresolved comments"></span>' : '';
      div.innerHTML = `<span>${escapeHtml(f.path.split('/').pop())}</span>${unresolvedDot}${renderCommentIcon('review', f.path)}<div class="file-stat"><span class="file-stat-add">+${f.additions}</span><span class="file-stat-del">-${f.deletions}</span></div>`;
      container.appendChild(div);
    });
  } else {
    const tree = buildFileTree(files);
    renderTreeNode(tree, container, '', 0);
  }

  var countEl = document.getElementById('fileCount');
  if (countEl) countEl.textContent = files.length;
  var badgeEl = document.getElementById('diffFileCount');
  if (badgeEl) badgeEl.textContent = t('badges.filesChanged', {count: DIFF_DATA.files.length});
}

function renderTreeNode(node, container, prefix, depth) {
  depth = depth || 0;
  var pad = 14 + depth * 14;
  Object.keys(node).sort((a, b) => {
    const aIsDir = !node[a].path;
    const bIsDir = !node[b].path;
    if (aIsDir && !bIsDir) return -1;
    if (!aIsDir && bIsDir) return 1;
    return a.localeCompare(b);
  }).forEach(key => {
    const val = node[key];
    if (val.path) {
      const div = document.createElement('div');
      div.className = 'file-item' + (state.selectedFile === val.path ? ' active' : '');
      div.style.paddingLeft = (pad + 14) + 'px';
      div.onclick = (e) => { if (!e.target.closest('.comment-icon')) selectFile(val.path); };
      var unresolvedDot = fileHasUnresolvedComments(val.path) ? '<span class="file-unresolved-dot" title="Has unresolved comments"></span>' : '';
      div.innerHTML = `<span>${escapeHtml(key)}</span>${unresolvedDot}${renderCommentIcon('review', val.path)}<div class="file-stat"><span class="file-stat-add">+${val.additions}</span><span class="file-stat-del">-${val.deletions}</span></div>`;
      container.appendChild(div);
    } else {
      const dir = document.createElement('div');
      dir.className = 'file-dir';
      dir.style.paddingLeft = pad + 'px';
      dir.innerHTML = `<span class="arrow">▼</span> ${escapeHtml(key)}/`;
      dir.onclick = (e) => { e.stopPropagation(); dir.classList.toggle('collapsed'); };
      container.appendChild(dir);

      const children = document.createElement('div');
      children.className = 'dir-children';
      renderTreeNode(val, children, prefix + key + '/', depth + 1);
      container.appendChild(children);
    }
  });
}

function selectFile(path) {
  state.selectedFile = path;
  renderFileList();
  renderDiff(path);
  var btn = document.getElementById('viewFileBtn');
  if (btn) btn.style.display = path ? '' : 'none';
}

function openSelectedFile() {
  if (state.selectedFile) showFilePreview(state.selectedFile);
}

function renderDiff(path) {
  const file = DIFF_DATA.files.find(f => f.path === path);
  if (!file) return;
  const container = document.getElementById('diffContent');
  container.innerHTML = '';

  const pathHeader = document.createElement('div');
  pathHeader.className = 'diff-path-header';
  pathHeader.style.cssText = 'padding: 6px 12px; font-size: 0.8rem; font-family: var(--font-mono); color: var(--text-secondary); background: var(--bg-secondary); border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px;';

  var showResolvedBtn = document.createElement('button');
  showResolvedBtn.className = 'btn btn-sm';
  showResolvedBtn.style.cssText = 'margin-left: auto; font-size: 0.7rem;';
  showResolvedBtn.textContent = _showResolved ? t('review.hideResolved') : t('review.showResolved');
  showResolvedBtn.onclick = function() {
    _showResolved = !_showResolved;
    renderDiff(path);
  };

  pathHeader.innerHTML = '<span style="opacity: 0.6;">📄</span> ' + escapeHtml(path) + ' <span style="font-size: 0.75rem; color: var(--text-muted);">+' + file.additions + ' −' + file.deletions + '</span>';
  pathHeader.appendChild(showResolvedBtn);
  container.appendChild(pathHeader);

  const targetEl = document.createElement('div');
  container.appendChild(targetEl);

  const ui = new Diff2HtmlUI(targetEl, file.diff, {
    drawFileList: false,
    matching: 'none',
    renderNothingWhenEmpty: true,
    outputFormat: state.diffMode,
    highlight: true,
    synchronisedScroll: true,
    stickyFileHeaders: false
  });
  ui.draw();
  ui.highlightCode();
  attachDiffLineClickHandlers(targetEl, path);
  renderDiffLineCommentIndicators(targetEl, path);
  autoExpandUnresolvedThreads(targetEl, path);
}

function getDiffLineNumber(td) {
  var text = td.textContent.trim();
  if (!text) return null;
  var match = text.match(/(\d+)/);
  if (!match) return null;
  return parseInt(match[1]);
}

function getDiffLineContent(tr) {
  var ctnEl = tr.querySelector('.d2h-code-line-ctn, .d2h-code-side-line-ctn');
  return ctnEl ? ctnEl.textContent : '';
}

function getDiffFilePath(td) {
  var fileWrapper = td.closest('.d2h-file-wrapper');
  if (fileWrapper) {
    var header = fileWrapper.querySelector('.d2h-file-name');
    if (header) return header.textContent.trim();
  }
  return null;
}

function attachDiffLineClickHandlers(container, filePath) {
  var lineNumCells = container.querySelectorAll('td.d2h-code-linenumber, td.d2h-code-side-linenumber');
  lineNumCells.forEach(function(td) {
    td.addEventListener('click', function(e) {
      e.stopPropagation();
      var lineNum = getDiffLineNumber(td);
      if (!lineNum) return;

      var tr = td.closest('tr');

      // Toggle: if a comment form/thread row is already open for this line, close it
      var existingRow = tr.nextElementSibling;
      if (existingRow && existingRow.classList.contains('line-comment-row')) {
        existingRow.remove();
        return;
      }

      var lineContent = getDiffLineContent(tr);
      var target = filePath;

      document.querySelectorAll('.diff-content .line-comment-row').forEach(function(el) { el.remove(); });

      var formRow = document.createElement('tr');
      formRow.className = 'line-comment-row';
      var formCell = document.createElement('td');
      var colSpan = tr.querySelectorAll('td').length;
      formCell.setAttribute('colspan', colSpan);
      formRow.appendChild(formCell);
      tr.parentNode.insertBefore(formRow, tr.nextSibling);

      var lineComments = getCommentsForLine(filePath, lineNum);
      lineComments.forEach(function(comment) {
        var thread = renderReviewThread(comment, {
          showFileInfo: false,
          onResolve: function(id) { resolveReviewComment(id); },
          onReply: function(id, text) { replyToReviewComment(id, text); }
        });
        formCell.appendChild(thread);
      });

      openLineCommentForm('review', target, filePath, lineNum, lineContent, formCell);
    });
  });
}

function renderDiffLineCommentIndicators(container, filePath) {
  var key = 'review:' + filePath;
  var allComments = COMMENTS[key] || [];
  var lineComments = {};
  allComments.forEach(function(c) {
    if (c.line_start != null && !c.parent_id && (!c.resolved || _showResolved)) {
      if (!lineComments[c.line_start]) lineComments[c.line_start] = [];
      lineComments[c.line_start].push(c);
    }
  });

  if (Object.keys(lineComments).length === 0) return;

  var lineNumCells = container.querySelectorAll('td.d2h-code-linenumber, td.d2h-code-side-linenumber');
  lineNumCells.forEach(function(td) {
    var lineNum = getDiffLineNumber(td);
    if (lineNum && lineComments[lineNum]) {
      var comments = lineComments[lineNum];
      var count = comments.length;
      var hasUnresolved = comments.some(function(c) { return !c.resolved; });
      var indicator = document.createElement('span');
      indicator.className = 'line-comment-indicator';
      indicator.innerHTML = '&#x1F4AC;';
      if (count > 1) {
        indicator.innerHTML += '<span class="line-comment-count">' + count + '</span>';
      }
      indicator.title = count + ' comment' + (count > 1 ? 's' : '');
      td.insertBefore(indicator, td.firstChild);
      var row = td.closest('tr');
      row.classList.add('line-has-comment');
      if (hasUnresolved) {
        row.classList.add('line-has-unresolved');
      }
    }
  });
}

function autoExpandUnresolvedThreads(container, filePath) {
  var key = 'review:' + filePath;
  var allComments = COMMENTS[key] || [];
  var unresolvedLines = {};
  allComments.forEach(function(c) {
    if (c.line_start != null && !c.parent_id && !c.resolved) {
      unresolvedLines[c.line_start] = true;
    }
  });

  if (Object.keys(unresolvedLines).length === 0) return;

  var lineNumCells = container.querySelectorAll('td.d2h-code-linenumber, td.d2h-code-side-linenumber');
  lineNumCells.forEach(function(td) {
    var lineNum = getDiffLineNumber(td);
    if (!lineNum || !unresolvedLines[lineNum]) return;

    var tr = td.closest('tr');
    if (tr.nextElementSibling && tr.nextElementSibling.classList.contains('line-comment-row')) return;

    var formRow = document.createElement('tr');
    formRow.className = 'line-comment-row';
    var formCell = document.createElement('td');
    var colSpan = tr.querySelectorAll('td').length;
    formCell.setAttribute('colspan', colSpan);
    formRow.appendChild(formCell);
    tr.parentNode.insertBefore(formRow, tr.nextSibling);

    var lineComments = getCommentsForLine(filePath, lineNum);
    lineComments.forEach(function(comment) {
      var thread = renderReviewThread(comment, {
        showFileInfo: false,
        onResolve: function(id) { resolveReviewComment(id); },
        onReply: function(id, text) { replyToReviewComment(id, text); }
      });
      formCell.appendChild(thread);
    });

    unresolvedLines[lineNum] = false;
  });
}

function getCommentsForLine(filePath, lineNum) {
  var key = 'review:' + filePath;
  var all = COMMENTS[key] || [];
  return all.filter(function(c) {
    if (c.parent_id) return false;
    if (c.resolved && !_showResolved) return false;
    return c.line_start <= lineNum && (c.line_end || c.line_start) >= lineNum;
  });
}

async function resolveReviewComment(commentId) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  try {
    await fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/comments/' + commentId + '/resolve', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({resolved: true})
    });
    await refreshComments();
  } catch(e) {
    showToast(t('messages.failedToResolve', {error: e.message}));
  }
}

async function replyToReviewComment(commentId, text) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  try {
    await fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/comments/' + commentId + '/reply', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text})
    });
    await refreshComments();
  } catch(e) {
    showToast(t('messages.failedToUpdate', {error: e.message}));
  }
}

async function refreshComments() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  var resp = await fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/comments?scope=review');
  var data = await resp.json();
  COMMENTS = {};
  (data.comments || []).forEach(function(c) {
    var key = 'review:' + c.file_path;
    if (!COMMENTS[key]) COMMENTS[key] = [];
    COMMENTS[key].push(c);
  });
  renderDiffView();
}

function renderDiffView() {
  renderFileList();
  if (state.selectedFile) renderDiff(state.selectedFile);
}

function setFileView(mode) {
  state.fileView = mode;
  localStorage.setItem('diff_fileView', mode);
  document.querySelectorAll('#viewModeToggle .toggle-opt').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  renderFileList();
}

function setDiffMode(mode) {
  state.diffMode = mode;
  localStorage.setItem('diff_diffMode', mode);
  document.querySelectorAll('#diffModeToggle .toggle-opt').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  if (state.selectedFile) renderDiff(state.selectedFile);
}

async function setDiffSource(mode) {
  localStorage.setItem('diff_diffSource', mode);
  state.diffSource = mode;
  document.querySelectorAll('#diffSourceToggle .toggle-opt').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  const ctx = getWorkspaceContext();
  if (!ctx) return;
  try {
    const diffData = await apiGetDiff(ctx.projectId, ctx.branch, mode);
    if (diffData && diffData.files) {
      DIFF_DATA = diffData;
    }
  } catch (e) {
    console.warn('Diff API unavailable:', e.message);
  }
  renderFileList();
}

// ═══════════════════════════════════════════════
//  RESIZABLE FILE LIST PANEL
// ═══════════════════════════════════════════════
makeResizable('diffResizeHandle', 'diffFileList');
