// ═══════════════════════════════════════════════
//  RESEARCH RENDER
// ═══════════════════════════════════════════════
function renderResearch() {
  var container = document.getElementById('researchFindings');
  container.innerHTML = '';

  var badge = document.getElementById('researchStatus');

  if (!RESEARCH_DATA || RESEARCH_DATA.length === 0) {
    container.innerHTML = '<div class="no-items-msg">' + t('research.noEntries') + '</div>';
    if (badge) { badge.textContent = ''; badge.className = 'badge'; }
    return;
  }

  var total = RESEARCH_DATA.length;
  var verified = RESEARCH_DATA.filter(function(e) { return e.proven === 1; }).length;
  var rejected = RESEARCH_DATA.filter(function(e) { return e.proven === -1; }).length;
  var pending = total - verified - rejected;
  if (badge) {
    badge.textContent = rejected > 0 ? t('research.verifiedRejectedCount', {verified: verified, total: total, rejected: rejected}) : t('research.verifiedCount', {verified: verified, total: total});
    badge.className = 'badge ' + (pending > 0 ? 'badge-warning' : rejected > 0 ? 'badge-danger' : 'badge-success');
  }

  RESEARCH_DATA.forEach(function(entry) {
    var topicName = entry.topic || t('research.untitledResearch');
    var proven = entry.proven;
    var badgeClass = proven === 1 ? 'success' : proven === -1 ? 'danger' : 'warning';
    var badgeText = proven === 1 ? t('badges.verified') : proven === -1 ? t('badges.rejected') : t('badges.pending');
    var findings = entry.findings || [];

    var group = document.createElement('div');
    group.className = 'research-group collapsed';
    if (entry.discussion_id) {
      group.dataset.discussionId = entry.discussion_id;
    }

    var header = document.createElement('div');
    header.className = 'research-group-header';
    var proveBtn = proven !== 1
      ? '<button class="research-action-btn research-prove-btn" data-id="' + entry.id + '" onclick="toggleResearchProven(' + entry.id + ', true, this); event.stopPropagation();" title="' + t('research.titleMarkVerified') + '">✓</button>'
      : '<button class="research-action-btn research-prove-btn active" disabled title="' + t('research.titleVerified') + '">✓</button>';
    var rejectBtn = proven !== -1
      ? '<button class="research-action-btn research-reject-btn" data-id="' + entry.id + '" onclick="toggleResearchProven(' + entry.id + ', false, this); event.stopPropagation();" title="' + t('research.titleMarkRejected') + '">✗</button>'
      : '<button class="research-action-btn research-reject-btn active" disabled title="' + t('research.titleRejected') + '">✗</button>';
    var deleteBtn = '<button class="research-action-btn research-delete-btn" onclick="deleteResearch(' + entry.id + '); event.stopPropagation();" title="' + t('research.titleDeleteEntry') + '">🗑</button>';

    var discussionBadge = entry.discussion_id
      ? '<span class="badge" style="font-size:0.6rem;background:var(--warning-dim);color:var(--warning);margin-left:4px;" title="' + t('research.linkedToDiscussion', {id: entry.discussion_id}) + '">D#' + entry.discussion_id + '</span>'
      : '';

    header.innerHTML =
      '<span class="research-group-title">' + escapeHtml(topicName) + '</span>' +
      discussionBadge +
      '<span class="research-group-count">' + t('research.findingCount', {count: findings.length}) + '</span>' +
      '<span class="badge badge-' + badgeClass + '">' + badgeText + '</span>' +
      '<span class="research-actions">' + proveBtn + rejectBtn + deleteBtn + '</span>';
    header.onclick = function() { group.classList.toggle('collapsed'); };
    group.appendChild(header);

    var body = document.createElement('div');
    body.className = 'research-group-body';

    if (entry.summary) {
      var entrySummaryEl = document.createElement('div');
      entrySummaryEl.className = 'research-group-summary';
      entrySummaryEl.textContent = entry.summary;
      body.appendChild(entrySummaryEl);
    }

    findings.forEach(function(f, i) {
      var div = document.createElement('div');
      div.className = 'finding';

      var summary = f.summary || '';
      var details = f.details || '';
      var proof = f.proof || {};

      var proofHtml = '';
      var snippetId = 'snippet-' + entry.id + '-' + i;
      var proofType = proof.type || 'code'; // default to code for backwards compat

      if (proofType === 'code' && proof.file) {
        var lineRange = proof.line_start && proof.line_end ? proof.line_start + '-' + proof.line_end : '';
        var label = proof.file + (lineRange ? ':' + lineRange : '');
        proofHtml = '<span class="finding-ref clickable" title="' + escapeHtml(label) + '" onclick="showFilePreview(\'' +
          proof.file.replace(/'/g, "\\'") + '\', ' +
          (proof.line_start || 0) + ', ' + (proof.line_end || 0) +
          ')">📄 ' + escapeHtml(label) + '</span>';
        // For code proofs: load snippet dynamically from server
        var hasSnippetRange = proof.snippet_start && proof.snippet_end;
        var hasLegacySnippet = proof.snippet;
        if (hasSnippetRange || hasLegacySnippet) {
          proofHtml += '<span class="finding-quote-btn" data-snippet-id="' + snippetId + '"' +
            (hasSnippetRange ? ' data-file="' + proof.file.replace(/"/g, '&quot;') + '"' +
            ' data-start="' + proof.snippet_start + '" data-end="' + proof.snippet_end + '"' : '') +
            ' onclick="toggleCodeSnippet(this)">' + t('research.showQuote') + '</span>';
        }
      } else if (proofType === 'web' && proof.url) {
        proofHtml = '<a class="finding-ref clickable" href="' + escapeHtml(proof.url) +
          '" target="_blank" rel="noopener">🌐 ' + escapeHtml(proof.title || proof.url) + '</a>';
      } else if (proofType === 'diff' && proof.commit) {
        var commitShort = proof.commit.substring(0, 7);
        var diffLabel = commitShort + (proof.file ? ' — ' + proof.file : '');
        proofHtml = '<span class="finding-ref">🔀 ' + escapeHtml(diffLabel) + '</span>';
        if (proof.description) {
          proofHtml += '<div class="finding-diff-desc">' + escapeHtml(proof.description) + '</div>';
        }
      } else if (proof.file) {
        // Legacy fallback — old format without type field
        var lineRange = proof.line_start && proof.line_end ? proof.line_start + '-' + proof.line_end : '';
        var label = proof.file + (lineRange ? ':' + lineRange : '');
        proofHtml = '<span class="finding-ref clickable" title="' + escapeHtml(label) + '" onclick="showFilePreview(\'' +
          proof.file.replace(/'/g, "\\'") + '\', ' +
          (proof.line_start || 0) + ', ' + (proof.line_end || 0) +
          ')">📄 ' + escapeHtml(label) + '</span>';
        if (proof.snippet) {
          proofHtml += '<span class="finding-quote-btn" onclick="toggleSnippet(\'' + snippetId + '\', this)">' + t('research.showQuote') + '</span>';
        }
      }

      var commentTarget = 'Finding: ' + summary.substring(0, 60);

      div.innerHTML =
        '<div class="finding-claim">' + escapeHtml(summary) + '</div>' +
        (proofHtml ? '<div style="margin-top: 4px;">' + proofHtml + '</div>' : '') +
        (proof.snippet ? '<div class="finding-snippet" id="' + snippetId + '"><code>' + escapeHtml(proof.snippet) + '</code></div>' :
         (proof.snippet_start && proof.snippet_end ? '<div class="finding-snippet" id="' + snippetId + '"><code>' + t('research.loading') + '</code></div>' : '')) +
        (proofType === 'web' && proof.quote ? '<div class="finding-snippet visible" style="border-left-color: var(--warning);"><code>' + escapeHtml(proof.quote) + '</code></div>' : '') +
        (details ? '<div class="finding-evidence">' + escapeHtml(details) + '</div>' : '') +
        '<div style="margin-top: 4px; text-align: right;">' + renderCommentIcon('research', commentTarget) + '</div>';
      body.appendChild(div);
    });

    group.appendChild(body);
    container.appendChild(group);
  });

  // Apply syntax highlighting to all snippets
  if (typeof hljs !== 'undefined') {
    container.querySelectorAll('.finding-snippet code').forEach(function(block) {
      hljs.highlightElement(block);
    });
  }
}

async function showFilePreview(filePath, startLine, endLine) {
  var modal = document.getElementById('filePreviewModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'filePreviewModal';
    modal.className = 'file-preview-modal';
    modal.onclick = function(e) { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = '<div class="file-preview-content">' +
      '<div class="file-preview-header">' +
      '<span class="file-preview-path" id="previewPath"></span>' +
      '<span class="file-preview-lines" id="previewLines"></span>' +
      '<button class="file-preview-close" onclick="document.getElementById(\'filePreviewModal\').classList.remove(\'open\')">&times;</button>' +
      '</div>' +
      '<div class="file-preview-body"><pre class="file-preview-code" id="previewCode"></pre></div>' +
      '</div>';
    document.body.appendChild(modal);
  }

  document.getElementById('previewPath').textContent = filePath;
  document.getElementById('previewLines').textContent = startLine && endLine ? t('research.linesRangeShort', {start: startLine, end: endLine}) : '';
  document.getElementById('previewCode').textContent = t('research.loading');
  modal.classList.add('open');

  var ctx = getWorkspaceContext();
  if (!ctx) {
    document.getElementById('previewCode').textContent = t('errors.noWorkspaceContext');
    return;
  }

  try {
    var isAbsolute = filePath.startsWith('/');
    var data = await apiReadFile(ctx.projectId, ctx.branch, filePath, startLine, endLine, isAbsolute);
    var lines = data.lines || [];
    var startNum = data.start || 1;
    var highlightStart = data.highlight_start;
    var highlightEnd = data.highlight_end;
    var ext = filePath.split('.').pop().toLowerCase();
    var isMarkdown = (ext === 'md' || ext === 'markdown' || ext === 'mdx');
    var codeEl = document.getElementById('previewCode');
    var bodyEl = codeEl.parentElement;

    if (isMarkdown) {
      var md = lines.join('\n');
      var rendered = document.createElement('div');
      rendered.className = 'file-preview-markdown';
      rendered.innerHTML = typeof marked !== 'undefined' ? DOMPurify.sanitize(marked.parse(md)) : escapeHtml(md);
      bodyEl.innerHTML = '';
      bodyEl.appendChild(rendered);
      // Highlight code blocks inside rendered markdown
      if (typeof hljs !== 'undefined') {
        rendered.querySelectorAll('pre code').forEach(function(block) { hljs.highlightElement(block); });
      }
    } else {
      bodyEl.innerHTML = '<pre class="file-preview-code" id="previewCode"></pre>';
      codeEl = document.getElementById('previewCode');
      var rawCode = lines.join('\n');
      var highlighted = null;
      if (typeof hljs !== 'undefined') {
        var langMap = { js: 'javascript', ts: 'typescript', py: 'python', rb: 'ruby', yml: 'yaml', sh: 'bash', zsh: 'bash', htm: 'html', jsx: 'javascript', tsx: 'typescript', rs: 'rust', kt: 'kotlin', swift: 'swift', go: 'go', cs: 'csharp', cpp: 'cpp', c: 'c', h: 'c', hpp: 'cpp', vue: 'xml', svelte: 'xml' };
        var lang = langMap[ext] || ext;
        try {
          highlighted = hljs.highlight(rawCode, { language: lang, ignoreIllegals: true }).value;
        } catch (e) {
          highlighted = hljs.highlightAuto(rawCode).value;
        }
      }

      if (highlighted) {
        var hLines = highlighted.split('\n');
        var html = '';
        hLines.forEach(function(line, i) {
          var lineNum = startNum + i;
          var isHl = highlightStart && highlightEnd && lineNum >= highlightStart && lineNum <= highlightEnd;
          var cls = isHl ? ' style="background: var(--accent-dim);"' : '';
          var lineComments = getLineComments('file', filePath, lineNum);
          var indicatorHtml = lineComments.length > 0 ? '<span class="line-comment-indicator" data-line="' + lineNum + '">' + lineComments.length + '</span>' : '';
          var hasCommentCls = lineComments.length > 0 ? ' line-has-comment' : '';
          html += '<div class="file-preview-line' + hasCommentCls + '"' + cls + '><span class="line-num line-num-clickable" data-line="' + lineNum + '">' + lineNum + '</span>' + line + indicatorHtml + '</div>';
        });
        codeEl.innerHTML = html;
      } else {
        var html = '';
        lines.forEach(function(line, i) {
          var lineNum = startNum + i;
          var isHl = highlightStart && highlightEnd && lineNum >= highlightStart && lineNum <= highlightEnd;
          var cls = isHl ? ' style="background: var(--accent-dim);"' : '';
          var lineComments = getLineComments('file', filePath, lineNum);
          var indicatorHtml = lineComments.length > 0 ? '<span class="line-comment-indicator" data-line="' + lineNum + '">' + lineComments.length + '</span>' : '';
          var hasCommentCls = lineComments.length > 0 ? ' line-has-comment' : '';
          html += '<div class="file-preview-line' + hasCommentCls + '"' + cls + '><span class="line-num line-num-clickable" data-line="' + lineNum + '">' + lineNum + '</span>' + escapeHtml(line) + indicatorHtml + '</div>';
        });
        codeEl.innerHTML = html;
      }

      attachFilePreviewLineClickHandlers(codeEl, filePath, lines, startNum);
    }

    document.getElementById('previewLines').textContent = isMarkdown ? t('research.lineCount', {count: lines.length}) : t('research.linesRange', {start: startNum, end: startNum + lines.length - 1, total: data.total_lines});
  } catch (e) {
    document.getElementById('previewCode').textContent = t('errors.failedToLoad', {error: e.message});
  }
}

function attachFilePreviewLineClickHandlers(codeEl, filePath, lines, startNum) {
  codeEl.querySelectorAll('.line-num-clickable').forEach(function(span) {
    span.addEventListener('click', function(e) {
      e.stopPropagation();
      var lineNum = parseInt(span.dataset.line);
      var lineIdx = lineNum - startNum;
      var lineContent = (lineIdx >= 0 && lineIdx < lines.length) ? lines[lineIdx] : '';
      var lineDiv = span.parentElement;

      openLineCommentForm('review', filePath, filePath, lineNum, lineContent, lineDiv);
    });
  });

  codeEl.querySelectorAll('.line-comment-indicator').forEach(function(indicator) {
    indicator.addEventListener('click', function(e) {
      e.stopPropagation();
      var lineNum = parseInt(indicator.dataset.line);
      var lineIdx = lineNum - startNum;
      var lineContent = (lineIdx >= 0 && lineIdx < lines.length) ? lines[lineIdx] : '';
      var lineDiv = indicator.closest('.file-preview-line');

      openLineCommentForm('review', filePath, filePath, lineNum, lineContent, lineDiv);
    });
  });
}

function toggleSnippet(id, btn) {
  var el = document.getElementById(id);
  if (!el) return;
  var visible = el.classList.toggle('visible');
  btn.textContent = visible ? t('research.hideQuote') : t('research.showQuote');
}

async function toggleResearchProven(entryId, proven, btn) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    var resp = await fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/research/' + entryId + '/prove', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({proven: proven})
    });
    if (resp.ok) {
      // Refresh the research data and re-render
      await refreshState();
    }
  } catch (e) {
    console.error('Failed to toggle research proven:', e);
  }
}

async function deleteResearch(entryId) {
  if (!confirm(t('dialog.deleteResearch'))) return;
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    var resp = await fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/research/' + entryId, {
      method: 'DELETE'
    });
    if (resp.ok) {
      await refreshState();
    }
  } catch (e) {
    console.error('Failed to delete research:', e);
  }
}

async function toggleCodeSnippet(btn) {
  var snippetId = btn.dataset.snippetId;
  var el = document.getElementById(snippetId);
  if (!el) return;

  var visible = el.classList.toggle('visible');
  btn.textContent = visible ? t('research.hideQuote') : t('research.showQuote');

  if (!visible) return;

  // If already loaded (not the loading placeholder), just show
  var codeEl = el.querySelector('code');
  if (codeEl && codeEl.dataset.loaded) return;

  // Load from server
  var file = btn.dataset.file;
  var start = parseInt(btn.dataset.start);
  var end = parseInt(btn.dataset.end);

  if (!file || !start || !end) return;

  var ctx = getWorkspaceContext();
  if (!ctx) {
    codeEl.textContent = t('errors.noWorkspaceContextAvailable');
    return;
  }

  try {
    var isAbsolute = file.startsWith('/');
    var data = await apiReadFile(ctx.projectId, ctx.branch, file, start, end, isAbsolute);
    var lines = data.lines || [];
    var rawCode = lines.join('\n');
    codeEl.dataset.loaded = 'true';

    if (typeof hljs !== 'undefined') {
      var ext = file.split('.').pop().toLowerCase();
      var langMap = { js: 'javascript', ts: 'typescript', py: 'python', rb: 'ruby', yml: 'yaml', sh: 'bash', htm: 'html', jsx: 'javascript', tsx: 'typescript', rs: 'rust', kt: 'kotlin', go: 'go', cs: 'csharp', cpp: 'cpp', c: 'c', java: 'java' };
      var lang = langMap[ext] || ext;
      try {
        codeEl.innerHTML = hljs.highlight(rawCode, { language: lang, ignoreIllegals: true }).value;
      } catch (e) {
        codeEl.innerHTML = hljs.highlightAuto(rawCode).value;
      }
    } else {
      codeEl.textContent = rawCode;
    }
  } catch (e) {
    codeEl.textContent = t('errors.failedToLoadSnippet', {error: e.message});
  }
}
