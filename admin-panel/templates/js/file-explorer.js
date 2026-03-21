// ═══════════════════════════════════════════════
//  FILE EXPLORER (lazy directory loading)
// ═══════════════════════════════════════════════

var explorerState = { selectedFile: null, filter: '', mdMode: 'preview', dirCache: {}, totalFiles: 0 };

function explorerApiUrl(ctx, params) {
  var url = '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/files';
  if (params) url += '?' + params;
  return url;
}

async function loadExplorerFiles() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  explorerState.dirCache = {};
  explorerState.filter = '';
  var searchInput = document.getElementById('fileExplorerSearch');
  if (searchInput) searchInput.value = '';
  try {
    var data = await apiGet(explorerApiUrl(ctx));
    explorerState.dirCache[''] = data.entries || [];
    explorerState.totalFiles = data.total || 0;
    renderExplorerLazy();
  } catch (e) {
    console.warn('Failed to load files:', e.message);
  }
}

async function expandExplorerDir(dirPath, dirEl) {
  if (dirEl.dataset.loading === 'true') return;

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  var childrenEl = dirEl.nextElementSibling;
  if (!childrenEl || !childrenEl.classList.contains('dir-children')) return;

  if (dirEl.classList.contains('collapsed')) {
    dirEl.classList.remove('collapsed');
    if (explorerState.dirCache[dirPath]) {
      if (!childrenEl.hasChildNodes()) {
        renderExplorerEntries(explorerState.dirCache[dirPath], childrenEl, dirPath);
      }
      childrenEl.style.display = '';
      return;
    }
    dirEl.dataset.loading = 'true';
    childrenEl.innerHTML = '<div style="padding: 6px 14px; font-size: 0.72rem; color: var(--text-muted);">Loading...</div>';
    childrenEl.style.display = '';
    try {
      var data = await apiGet(explorerApiUrl(ctx, 'path=' + encodeURIComponent(dirPath)));
      explorerState.dirCache[dirPath] = data.entries || [];
      childrenEl.innerHTML = '';
      renderExplorerEntries(data.entries || [], childrenEl, dirPath);
    } catch (e) {
      childrenEl.innerHTML = '<div style="padding: 6px 14px; font-size: 0.72rem; color: var(--danger);">Failed to load</div>';
    }
    delete dirEl.dataset.loading;
  } else {
    dirEl.classList.add('collapsed');
    childrenEl.style.display = 'none';
  }
}

function renderExplorerEntries(entries, container, parentPath) {
  var depth = parentPath ? parentPath.split('/').length : 0;
  var pad = 11 + depth * 11;

  entries.forEach(function(entry) {
    if (entry.type === 'dir') {
      var dir = document.createElement('div');
      dir.className = 'file-dir collapsed';
      dir.style.paddingLeft = pad + 'px';
      dir.innerHTML = '<span class="arrow">\u25BC</span> ' + escapeHtml(entry.name) + '/';
      dir.onclick = function(e) { e.stopPropagation(); expandExplorerDir(entry.path, dir); };
      container.appendChild(dir);

      var children = document.createElement('div');
      children.className = 'dir-children';
      children.style.display = 'none';
      container.appendChild(children);
    } else {
      var div = document.createElement('div');
      div.className = 'file-item' + (explorerState.selectedFile === entry.path ? ' active' : '');
      div.style.paddingLeft = (pad + 11) + 'px';
      div.dataset.path = entry.path;
      div.onclick = function() { selectExplorerFile(entry.path); };
      div.innerHTML = '<span>' + escapeHtml(entry.name) + '</span>';
      container.appendChild(div);
    }
  });
}

function renderExplorerLazy() {
  var container = document.getElementById('explorerFileList');
  var header = container.querySelector('.diff-file-list-header');
  container.innerHTML = '';
  container.appendChild(header);

  var countEl = document.getElementById('explorerCount');
  if (countEl) countEl.textContent = explorerState.totalFiles;
  var badgeEl = document.getElementById('explorerFileCount');
  if (badgeEl) badgeEl.textContent = explorerState.totalFiles + ' files';

  var entries = explorerState.dirCache[''] || [];
  renderExplorerEntries(entries, container, '');
}

var _explorerSearchTimeout = null;

async function filterExplorerFiles(query) {
  explorerState.filter = query.trim().toLowerCase();
  if (_explorerSearchTimeout) clearTimeout(_explorerSearchTimeout);

  if (!explorerState.filter) {
    renderExplorerLazy();
    return;
  }

  _explorerSearchTimeout = setTimeout(async function() {
    var ctx = getWorkspaceContext();
    if (!ctx) return;
    try {
      var data = await apiGet(explorerApiUrl(ctx, 'search=' + encodeURIComponent(explorerState.filter)));
      var container = document.getElementById('explorerFileList');
      var header = container.querySelector('.diff-file-list-header');
      container.innerHTML = '';
      container.appendChild(header);

      var entries = data.entries || [];
      var countEl = document.getElementById('explorerCount');
      if (countEl) countEl.textContent = entries.length;
      var badgeEl = document.getElementById('explorerFileCount');
      if (badgeEl) badgeEl.textContent = entries.length + ' results';

      entries.forEach(function(entry) {
        var div = document.createElement('div');
        div.className = 'file-item' + (explorerState.selectedFile === entry.path ? ' active' : '');
        div.dataset.path = entry.path;
        div.onclick = function() { selectExplorerFile(entry.path); };
        div.innerHTML = '<span>' + escapeHtml(entry.path) + '</span>';
        container.appendChild(div);
      });
    } catch (e) {
      console.warn('Search failed:', e.message);
    }
  }, 300);
}

var _explorerFileLines = [];

async function selectExplorerFile(path) {
  explorerState.selectedFile = path;
  explorerState.mdMode = 'preview';
  var fileList = document.getElementById('explorerFileList');
  if (fileList) {
    fileList.querySelectorAll('.file-item').forEach(function(el) {
      if (el.dataset.path === path) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    });
  }

  var content = document.getElementById('explorerContent');
  content.innerHTML = '<div class="diff-placeholder">' + t('explorer.loading') + '</div>';

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    var data = await apiReadFile(ctx.projectId, ctx.branch, path);
    _explorerFileLines = data.lines || [];
    renderExplorerContent(path, _explorerFileLines);
  } catch (e) {
    content.innerHTML = '<div class="diff-placeholder">' + t('explorer.failedToLoad', {error: escapeHtml(e.message)}) + '</div>';
  }
}

function isMarkdownFile(path) {
  var ext = path.split('.').pop().toLowerCase();
  return ext === 'md' || ext === 'markdown' || ext === 'mdx';
}

function renderExplorerContent(path, lines) {
  var content = document.getElementById('explorerContent');
  var ext = path.split('.').pop().toLowerCase();
  var isMd = isMarkdownFile(path);

  var headerHtml = '<div class="explorer-file-header">' + escapeHtml(path);
  if (isMd && typeof marked !== 'undefined') {
    headerHtml += '<div class="toggle-group md-toggle" style="margin-left: 12px;">' +
      '<button class="toggle-opt' + (explorerState.mdMode === 'source' ? ' active' : '') + '" data-mode="source" onclick="setExplorerMdMode(\'source\')">' + t('buttons.source') + '</button>' +
      '<button class="toggle-opt' + (explorerState.mdMode === 'preview' ? ' active' : '') + '" data-mode="preview" onclick="setExplorerMdMode(\'preview\')">' + t('buttons.preview') + '</button>' +
      '</div>';
  }
  headerHtml += '<span class="explorer-line-count">' + lines.length + ' lines</span></div>';

  if (isMd && typeof marked !== 'undefined' && explorerState.mdMode === 'preview') {
    var parsed = DOMPurify.sanitize(marked.parse(lines.join('\n')));
    var tmp = document.createElement('div');
    tmp.innerHTML = parsed;
    tmp.querySelectorAll('code').forEach(function(el) {
      el.innerHTML = el.innerHTML.replace(/&amp;lt;/g, '&lt;').replace(/&amp;gt;/g, '&gt;').replace(/&amp;amp;/g, '&amp;');
    });
    content.innerHTML = headerHtml +
      '<div class="explorer-file-body md-preview">' + tmp.innerHTML + '</div>';
    if (typeof hljs !== 'undefined') {
      content.querySelectorAll('pre code').forEach(function(block) { hljs.highlightElement(block); });
    }
  } else {
    var lang = LANG_MAP[ext] || ext;

    var numbered = lines.map(function(line, i) {
      return '<tr><td class="explorer-line-num">' + (i + 1) + '</td><td class="explorer-line-code">' + escapeHtml(line) + '</td></tr>';
    }).join('');

    content.innerHTML = headerHtml +
      '<div class="explorer-file-body"><table class="explorer-code-table"><tbody>' + numbered + '</tbody></table></div>';

    if (typeof hljs !== 'undefined') {
      var codeLines = content.querySelectorAll('.explorer-line-code');
      codeLines.forEach(function(td) {
        var result = hljs.highlight(td.textContent, { language: lang, ignoreIllegals: true });
        td.innerHTML = result.value;
      });
    }
  }
}

function setExplorerMdMode(mode) {
  explorerState.mdMode = mode;
  if (_explorerFileLines.length > 0 && explorerState.selectedFile) {
    renderExplorerContent(explorerState.selectedFile, _explorerFileLines);
  }
  document.querySelectorAll('.md-toggle .toggle-opt').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
}

// Resize handle for explorer panel
makeResizable('explorerResizeHandle', 'explorerFileList');
