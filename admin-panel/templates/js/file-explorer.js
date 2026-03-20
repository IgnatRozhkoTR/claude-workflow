// ═══════════════════════════════════════════════
//  FILE EXPLORER
// ═══════════════════════════════════════════════

var EXPLORER_DATA = { files: [], filtered: [] };
var explorerState = { view: 'tree', selectedFile: null, filter: '', mdMode: 'preview' };

async function loadExplorerFiles() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  try {
    var data = await apiGet('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/files');
    EXPLORER_DATA.files = data.files || [];
    EXPLORER_DATA.filtered = EXPLORER_DATA.files;
    renderExplorerFileList();
  } catch (e) {
    console.warn('Failed to load files:', e.message);
  }
}

function filterExplorerFiles(query) {
  explorerState.filter = query.toLowerCase();
  if (!explorerState.filter) {
    EXPLORER_DATA.filtered = EXPLORER_DATA.files;
  } else {
    EXPLORER_DATA.filtered = EXPLORER_DATA.files.filter(function(f) {
      var name = f.split('/').pop().toLowerCase();
      return name.indexOf(explorerState.filter) !== -1;
    });
  }
  renderExplorerFileList();
}

function buildExplorerTree(files) {
  var tree = {};
  files.forEach(function(path) {
    var parts = path.split('/');
    var node = tree;
    parts.forEach(function(part, i) {
      if (i === parts.length - 1) {
        node[part] = { _path: path };
      } else {
        if (!node[part] || node[part]._path) node[part] = node[part] || {};
        node = node[part];
      }
    });
  });
  return tree;
}

function renderExplorerTreeNode(node, container, depth) {
  depth = depth || 0;
  var pad = 11 + depth * 11;
  Object.keys(node).sort(function(a, b) {
    var aIsDir = !node[a]._path;
    var bIsDir = !node[b]._path;
    if (aIsDir && !bIsDir) return -1;
    if (!aIsDir && bIsDir) return 1;
    return a.localeCompare(b);
  }).forEach(function(key) {
    var val = node[key];
    if (val._path) {
      var div = document.createElement('div');
      div.className = 'file-item' + (explorerState.selectedFile === val._path ? ' active' : '');
      div.style.paddingLeft = (pad + 11) + 'px';
      div.dataset.path = val._path;
      div.onclick = function() { selectExplorerFile(val._path); };
      div.innerHTML = '<span>' + escapeHtml(key) + '</span>';
      container.appendChild(div);
    } else {
      var displayName = key;
      var currentSubtree = val;
      while (true) {
        var subKeys = Object.keys(currentSubtree).filter(function(k) { return !currentSubtree[k]._path; });
        var subFiles = Object.keys(currentSubtree).filter(function(k) { return currentSubtree[k]._path; });
        if (subKeys.length === 1 && subFiles.length === 0) {
          displayName += '/' + subKeys[0];
          currentSubtree = currentSubtree[subKeys[0]];
        } else {
          break;
        }
      }

      var dir = document.createElement('div');
      dir.className = 'file-dir';
      dir.style.paddingLeft = pad + 'px';
      dir.innerHTML = '<span class="arrow">\u25BC</span> ' + escapeHtml(displayName) + '/';
      dir.onclick = function(e) { e.stopPropagation(); dir.classList.toggle('collapsed'); };
      container.appendChild(dir);

      var children = document.createElement('div');
      children.className = 'dir-children';
      renderExplorerTreeNode(currentSubtree, children, depth + 1);
      container.appendChild(children);
    }
  });
}

function renderExplorerFileList() {
  var container = document.getElementById('explorerFileList');
  var header = container.querySelector('.diff-file-list-header');
  container.innerHTML = '';
  container.appendChild(header);

  var files = EXPLORER_DATA.filtered;
  var countEl = document.getElementById('explorerCount');
  if (countEl) countEl.textContent = files.length;
  var badgeEl = document.getElementById('explorerFileCount');
  if (badgeEl) badgeEl.textContent = t('badges.fileCount', {count: files.length});

  if (explorerState.view === 'flat') {
    files.forEach(function(path) {
      var div = document.createElement('div');
      div.className = 'file-item' + (explorerState.selectedFile === path ? ' active' : '');
      div.dataset.path = path;
      div.onclick = function() { selectExplorerFile(path); };
      div.innerHTML = '<span>' + escapeHtml(path) + '</span>';
      container.appendChild(div);
    });
  } else {
    var tree = buildExplorerTree(files);
    renderExplorerTreeNode(tree, container, 0);
  }
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
    var parsed = marked.parse(lines.join('\n'));
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
    var lang = ext;
    var langMap = { kt: 'kotlin', py: 'python', js: 'javascript', ts: 'typescript', yml: 'yaml', sh: 'bash', rb: 'ruby', rs: 'rust' };
    if (langMap[ext]) lang = langMap[ext];

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
  if (explorerState.selectedFile) {
    renderExplorerContent(explorerState.selectedFile, _explorerFileLines);
  }
}

function setExplorerView(mode) {
  explorerState.view = mode;
  document.querySelectorAll('#fileExplorerViewToggle .toggle-opt').forEach(function(b) {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
  renderExplorerFileList();
}

// Resize handle for explorer panel
makeResizable('explorerResizeHandle', 'explorerFileList');
