// ═══════════════════════════════════════════════
//  FILE EXPLORER
// ═══════════════════════════════════════════════

var EXPLORER_DATA = { files: [], filtered: [] };
var explorerState = { view: 'tree', selectedFile: null, filter: '' };

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
  var pad = 14 + depth * 14;
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
      div.style.paddingLeft = (pad + 14) + 'px';
      div.onclick = function() { selectExplorerFile(val._path); };
      div.innerHTML = '<span>' + escapeHtml(key) + '</span>';
      container.appendChild(div);
    } else {
      var dir = document.createElement('div');
      dir.className = 'file-dir';
      dir.style.paddingLeft = pad + 'px';
      dir.innerHTML = '<span class="arrow">\u25BC</span> ' + escapeHtml(key) + '/';
      dir.onclick = function(e) { e.stopPropagation(); dir.classList.toggle('collapsed'); };
      container.appendChild(dir);

      var children = document.createElement('div');
      children.className = 'dir-children';
      renderExplorerTreeNode(val, children, depth + 1);
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
      div.onclick = function() { selectExplorerFile(path); };
      div.innerHTML = '<span>' + escapeHtml(path) + '</span>';
      container.appendChild(div);
    });
  } else {
    var tree = buildExplorerTree(files);
    renderExplorerTreeNode(tree, container, 0);
  }
}

async function selectExplorerFile(path) {
  explorerState.selectedFile = path;
  renderExplorerFileList();

  var content = document.getElementById('explorerContent');
  content.innerHTML = '<div class="diff-placeholder">' + t('explorer.loading') + '</div>';

  var ctx = getWorkspaceContext();
  if (!ctx) return;

  try {
    var data = await apiReadFile(ctx.projectId, ctx.branch, path);
    var lines = data.lines || [];
    var ext = path.split('.').pop().toLowerCase();
    var isMarkdown = (ext === 'md' || ext === 'markdown' || ext === 'mdx');

    if (isMarkdown && typeof marked !== 'undefined') {
      content.innerHTML = '<div class="explorer-file-header">' + escapeHtml(path) +
        '<span class="explorer-line-count">' + lines.length + ' lines</span></div>' +
        '<div class="explorer-file-body explorer-markdown">' + marked.parse(escapeHtml(lines.join('\n'))) + '</div>';
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

      content.innerHTML = '<div class="explorer-file-header">' + escapeHtml(path) +
        '<span class="explorer-line-count">' + lines.length + ' lines</span></div>' +
        '<div class="explorer-file-body"><table class="explorer-code-table"><tbody>' + numbered + '</tbody></table></div>';

      if (typeof hljs !== 'undefined') {
        var codeLines = content.querySelectorAll('.explorer-line-code');
        codeLines.forEach(function(td) {
          var result = hljs.highlight(td.textContent, { language: lang, ignoreIllegals: true });
          td.innerHTML = result.value;
        });
      }
    }
  } catch (e) {
    content.innerHTML = '<div class="diff-placeholder">' + t('explorer.failedToLoad', {error: escapeHtml(e.message)}) + '</div>';
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
