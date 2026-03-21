// ═══════════════════════════════════════════════
//  SHARED TREE UTILITIES
// ═══════════════════════════════════════════════

var LANG_MAP = {
  js: 'javascript', jsx: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  py: 'python',
  rb: 'ruby',
  yml: 'yaml',
  sh: 'bash', zsh: 'bash',
  htm: 'html',
  rs: 'rust',
  kt: 'kotlin',
  swift: 'swift',
  go: 'go',
  cs: 'csharp',
  cpp: 'cpp', hpp: 'cpp',
  c: 'c', h: 'c',
  java: 'java',
  vue: 'xml', svelte: 'xml'
};

function buildFileTree(items, pathFn) {
  var tree = {};
  items.forEach(function(item) {
    var parts = pathFn(item).split('/');
    var node = tree;
    parts.forEach(function(part, i) {
      if (i === parts.length - 1) {
        node[part] = item;
      } else {
        if (!node[part] || typeof node[part] !== 'object' || pathFn(node[part])) node[part] = {};
        node = node[part];
      }
    });
  });
  return tree;
}

function renderTreeNode(node, container, depth, options) {
  depth = depth || 0;
  options = options || {};
  var pathFn = options.pathFn || function(item) { return item.path; };
  var pad = 11 + depth * 11;

  Object.keys(node).sort(function(a, b) {
    var aIsDir = !pathFn(node[a]);
    var bIsDir = !pathFn(node[b]);
    if (aIsDir && !bIsDir) return -1;
    if (!aIsDir && bIsDir) return 1;
    return a.localeCompare(b);
  }).forEach(function(key) {
    var val = node[key];
    if (pathFn(val)) {
      var div = document.createElement('div');
      var itemPath = pathFn(val);
      div.className = 'file-item' + (options.isSelected && options.isSelected(itemPath) ? ' active' : '');
      div.style.paddingLeft = (pad + 11) + 'px';
      div.dataset.path = itemPath;
      div.onclick = function(e) {
        if (options.onClick) options.onClick(e, val, key);
      };
      div.innerHTML = options.renderFileContent ? options.renderFileContent(val, key) : '<span>' + escapeHtml(key) + '</span>';
      container.appendChild(div);
    } else {
      var displayName = key;
      var currentSubtree = val;
      while (true) {
        var subKeys = Object.keys(currentSubtree).filter(function(k) { return !pathFn(currentSubtree[k]); });
        var subFiles = Object.keys(currentSubtree).filter(function(k) { return pathFn(currentSubtree[k]); });
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
      renderTreeNode(currentSubtree, children, depth + 1, options);
      container.appendChild(children);
    }
  });
}
