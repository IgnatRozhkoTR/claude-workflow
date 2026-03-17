// ═══════════════════════════════════════════════
//  DIAGRAM ZOOM & PAN
// ═══════════════════════════════════════════════

// Diagram zoom state
let diagramScale = 1.0;
let systemDiagramScale = 1.0;

function zoomDiagram(delta) {
  diagramScale = Math.max(0.4, Math.min(2.5, diagramScale + delta));
  const svg = document.querySelector('#planDiagram svg');
  if (svg) svg.style.transform = `scale(${diagramScale})`;
  const label = document.getElementById('diagramZoomLevel');
  if (label) label.textContent = Math.round(diagramScale * 100) + '%';
}

function zoomSystemDiagram(delta) {
  systemDiagramScale = Math.max(0.4, Math.min(2.5, systemDiagramScale + delta));
  const svg = document.querySelector('#systemDiagram svg');
  if (svg) svg.style.transform = `scale(${systemDiagramScale})`;
  const label = document.getElementById('systemDiagramZoomLevel');
  if (label) label.textContent = Math.round(systemDiagramScale * 100) + '%';
}

// Diagram pan (drag to scroll) — planDiagram
(function() {
  let isDragging = false;
  let startX, startY, scrollLeft, scrollTop;

  document.addEventListener('mousedown', function(e) {
    const container = document.getElementById('planDiagram');
    if (!container || !container.contains(e.target)) return;
    if (e.target.closest('button') || e.target.closest('.comment-icon')) return;
    isDragging = true;
    container.classList.add('dragging');
    startX = e.pageX - container.offsetLeft;
    startY = e.pageY - container.offsetTop;
    scrollLeft = container.scrollLeft;
    scrollTop = container.scrollTop;
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    const container = document.getElementById('planDiagram');
    if (!container) return;
    const x = e.pageX - container.offsetLeft;
    const y = e.pageY - container.offsetTop;
    container.scrollLeft = scrollLeft - (x - startX);
    container.scrollTop = scrollTop - (y - startY);
  });

  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    const container = document.getElementById('planDiagram');
    if (container) container.classList.remove('dragging');
  });
})();

// Diagram pan (drag to scroll) — systemDiagram
(function() {
  let isDragging = false;
  let startX, startY, scrollLeft, scrollTop;

  document.addEventListener('mousedown', function(e) {
    const container = document.getElementById('systemDiagram');
    if (!container || !container.contains(e.target)) return;
    if (e.target.closest('button') || e.target.closest('.comment-icon') || e.target.closest('.comment-icon-header')) return;
    isDragging = true;
    container.classList.add('dragging');
    startX = e.pageX - container.offsetLeft;
    startY = e.pageY - container.offsetTop;
    scrollLeft = container.scrollLeft;
    scrollTop = container.scrollTop;
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    const container = document.getElementById('systemDiagram');
    if (!container) return;
    const x = e.pageX - container.offsetLeft;
    const y = e.pageY - container.offsetTop;
    container.scrollLeft = scrollLeft - (x - startX);
    container.scrollTop = scrollTop - (y - startY);
  });

  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    const container = document.getElementById('systemDiagram');
    if (container) container.classList.remove('dragging');
  });
})();

// Diagram pan (drag to scroll) — overlay
(function() {
  let isDragging = false;
  let startX, startY, scrollLeft, scrollTop;

  document.addEventListener('mousedown', function(e) {
    const container = document.getElementById('diagramOverlayBody');
    if (!container || !container.contains(e.target)) return;
    if (e.target.closest('button') || e.target.closest('.diagram-overlay-controls')) return;
    isDragging = true;
    container.style.cursor = 'grabbing';
    startX = e.pageX - container.offsetLeft;
    startY = e.pageY - container.offsetTop;
    scrollLeft = container.scrollLeft;
    scrollTop = container.scrollTop;
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    const container = document.getElementById('diagramOverlayBody');
    if (!container) return;
    const x = e.pageX - container.offsetLeft;
    const y = e.pageY - container.offsetTop;
    container.scrollLeft = scrollLeft - (x - startX);
    container.scrollTop = scrollTop - (y - startY);
  });

  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    const container = document.getElementById('diagramOverlayBody');
    if (container) container.style.cursor = 'grab';
  });
})();

// ═══════════════════════════════════════════════
//  SYSTEM DIAGRAM RENDER
// ═══════════════════════════════════════════════

async function renderSystemDiagram() {
  var container = document.getElementById('systemDiagram');
  if (!container || typeof mermaid === 'undefined') return;

  var raw = PLAN_DATA.systemDiagram;
  if (!raw || (Array.isArray(raw) && raw.length === 0)) {
    container.innerHTML = '<p style="color:var(--text-muted);padding:16px;">' + t('plan.noSystemDiagram') + '</p>';
    return;
  }

  var diagrams;
  if (typeof raw === 'string') {
    diagrams = [{ title: '', diagram: raw }];
  } else if (Array.isArray(raw)) {
    diagrams = raw;
  } else {
    container.innerHTML = '<p style="color:var(--text-muted);padding:16px;">' + t('plan.invalidDiagramFormat') + '</p>';
    return;
  }

  container.innerHTML = '';

  for (var idx = 0; idx < diagrams.length; idx++) {
    var entry = diagrams[idx];
    var diagramText = entry.diagram || '';
    if (!diagramText.trim()) continue;

    if (entry.title) {
      var titleEl = document.createElement('h4');
      titleEl.className = 'diagram-subtitle';
      titleEl.textContent = entry.title;
      container.appendChild(titleEl);
    }

    var diagramDiv = document.createElement('div');
    diagramDiv.className = 'diagram-section';
    diagramDiv.id = 'systemDiagram_' + idx;
    container.appendChild(diagramDiv);

    var themed = diagramText;
    if (typeof getMermaidInit === 'function') {
      themed = diagramText.replace(/%%\{init:[\s\S]*?\}%%/g, getMermaidInit());
      if (themed === diagramText && !diagramText.includes('%%{init:')) {
        themed = getMermaidInit() + '\n' + diagramText;
      }
    }

    // Replace hardcoded rect colors with theme-appropriate alternatives
    if (typeof getMermaidTheme === 'function') {
      var isDarkTheme = (localStorage.getItem('admin-panel-theme') || 'dark') === 'dark';
      var rectColors = isDarkTheme
        ? ['rgba(40, 40, 60, 0.5)', 'rgba(40, 60, 40, 0.5)', 'rgba(60, 40, 40, 0.5)']
        : ['rgba(200, 210, 230, 0.3)', 'rgba(200, 230, 210, 0.3)', 'rgba(230, 210, 200, 0.3)'];
      var colorIdx = 0;
      themed = themed.replace(/rect\s+rgb\s*\([^)]+\)/g, function() {
        var color = rectColors[colorIdx % rectColors.length];
        colorIdx++;
        return 'rect ' + color;
      });
      themed = themed.replace(/rect\s+#[0-9a-fA-F]{3,8}/g, function() {
        var color = rectColors[colorIdx % rectColors.length];
        colorIdx++;
        return 'rect ' + color;
      });
    }

    try {
      var renderResult = await mermaid.render('sysDiag_' + idx, themed);
      diagramDiv.innerHTML = renderResult.svg;
    } catch (e) {
      console.error('System diagram render failed:', e);
      diagramDiv.innerHTML = '<pre style="color:var(--text-muted);padding:8px;">Diagram render error: ' + escapeHtml(e.message) + '</pre>';
    }
  }
}

// ═══════════════════════════════════════════════
//  PLAN RENDER
// ═══════════════════════════════════════════════

function getGroupStatus(group) {
  const done = group.tasks.filter(t => t.status === 'done').length;
  const total = group.tasks.length;
  if (done === total) return 'all-done';
  if (done > 0) return 'partial';
  return 'pending';
}

function truncateLabel(text, maxLen) {
  if (!text || text.length <= maxLen) return text;
  return text.substring(0, maxLen - 1) + '…';
}

function buildMermaidDiagram(direction) {
  direction = direction || 'LR';
  var isDark = (localStorage.getItem('admin-panel-theme') || 'dark') === 'dark';
  var colors = isDark
    ? { done: 'fill:#2d4a2d,stroke:#6bc77a,color:#e8e6e1', progress: 'fill:#4a4a2d,stroke:#c7b76b,color:#e8e6e1', pending: 'fill:#2d3250,stroke:#4a5078,color:#f0ede8', dot: 'fill:#4a5078,stroke:#8888a0,color:#4a5078' }
    : { done: 'fill:#d4edda,stroke:#2e8540,color:#1a1a18', progress: 'fill:#fff3cd,stroke:#b8860b,color:#1a1a18', pending: 'fill:#e8edf3,stroke:#c5cdd8,color:#1a1a18', dot: 'fill:#c5cdd8,stroke:#8b8fa3,color:#c5cdd8' };
  var items = PLAN_DATA.execution || PLAN_DATA.groups || [];
  if (items.length === 0) return '';

  var innerDirection = direction === 'TD' ? 'LR' : 'TB';

  var lines = [
    (typeof getMermaidInit === 'function' ? getMermaidInit() : "%%{init: {'theme': 'dark'}}%%"),
    'graph ' + direction
  ];

  var lastSubPhaseNodes = [];

  items.forEach(function(item, i) {
    var tasks = item.tasks || [];
    var subId = 'S' + (i + 1);
    var subLabel = escapeHtml(item.id || '') + ' — ' + escapeHtml(truncateLabel(item.name || t('phase.phaseName', {phase: i + 1}), 40));

    lines.push('    subgraph ' + subId + '["' + subLabel + '"]');
    lines.push('    direction ' + innerDirection);

    if (tasks.length === 0) {
      var emptyId = subId + '_empty';
      lines.push('        ' + emptyId + '["' + t('plan.noTasks') + '"]');
      lines.push('    end');
      if (lastSubPhaseNodes.length > 0) {
        lastSubPhaseNodes.forEach(function(ln) { lines.push('    ' + ln + ' --> ' + emptyId); });
      }
      lastSubPhaseNodes = [emptyId];
      return;
    }

    // Group tasks by group field
    var groupOrder = [];
    var groupMap = {};
    tasks.forEach(function(task, j) {
      var g = task.group || ('_solo_' + j);
      if (!groupMap[g]) {
        groupMap[g] = [];
        groupOrder.push(g);
      }
      groupMap[g].push({task: task, index: j});
    });

    var lastGroupNodes = [];

    groupOrder.forEach(function(groupName, gi) {
      var members = groupMap[groupName];
      var isParallelGroup = members.length > 1;
      var groupId = subId + '_G' + gi;

      // Create task node IDs
      var taskIds = members.map(function(m) { return subId + '_T' + (m.index + 1); });

      // Render task nodes
      members.forEach(function(m, mi) {
        var tId = taskIds[mi];
        var agentBadge = m.task.agent ? '<br/>' + escapeHtml(m.task.agent) : '';
        var label = escapeHtml(truncateLabel(m.task.title || t('plan.task', {n: m.index + 1}), 50)) + agentBadge;
        lines.push('        ' + tId + '["' + label + '"]');
      });

      var groupFirstNodes, groupLastNodes;

      if (isParallelGroup) {
        var forkId = groupId + '_fork';
        var joinId = groupId + '_join';
        lines.push('        ' + forkId + '(( ))');
        lines.push('        ' + joinId + '(( ))');
        lines.push('    style ' + forkId + ' ' + colors.dot);
        lines.push('    style ' + joinId + ' ' + colors.dot);
        taskIds.forEach(function(tId) {
          lines.push('        ' + forkId + ' --> ' + tId);
          lines.push('        ' + tId + ' --> ' + joinId);
        });
        groupFirstNodes = [forkId];
        groupLastNodes = [joinId];
      } else {
        for (var k = 1; k < taskIds.length; k++) {
          lines.push('        ' + taskIds[k - 1] + ' --> ' + taskIds[k]);
        }
        groupFirstNodes = [taskIds[0]];
        groupLastNodes = [taskIds[taskIds.length - 1]];
      }

      // Chain from previous group
      if (lastGroupNodes.length > 0) {
        lastGroupNodes.forEach(function(ln) {
          groupFirstNodes.forEach(function(fn) {
            lines.push('    ' + ln + ' --> ' + fn);
          });
        });
      }
      lastGroupNodes = groupLastNodes;
    });

    lines.push('    end');

    // Task status styling
    tasks.forEach(function(task, j) {
      var tId = subId + '_T' + (j + 1);
      if (task.status === 'done') {
        lines.push('    style ' + tId + ' ' + colors.done);
      } else if (task.status === 'in_progress') {
        lines.push('    style ' + tId + ' ' + colors.progress);
      }
    });

    // Default style for pending tasks (ensure visibility)
    tasks.forEach(function(task, j) {
      var tId = subId + '_T' + (j + 1);
      if (!task.status || task.status === 'pending') {
        lines.push('    style ' + tId + ' ' + colors.pending);
      }
    });

    // Chain from previous sub-phase
    if (lastSubPhaseNodes.length > 0 && groupOrder.length > 0) {
      var firstGroup = groupMap[groupOrder[0]];
      var firstGroupIsParallel = firstGroup.length > 1;
      var entryNodes = firstGroupIsParallel ? [subId + '_G0_fork'] : [subId + '_T' + (firstGroup[0].index + 1)];
      lastSubPhaseNodes.forEach(function(ln) {
        entryNodes.forEach(function(en) {
          lines.push('    ' + ln + ' --> ' + en);
        });
      });
    }
    lastSubPhaseNodes = lastGroupNodes || [];
  });

  return lines.join('\n');
}

async function renderMermaidDiagram() {
  const container = document.getElementById('planDiagram');
  if (!container || typeof mermaid === 'undefined') return;

  const definition = buildMermaidDiagram('LR');
  if (!definition) {
    container.innerHTML = '';
    return;
  }

  try {
    const { svg } = await mermaid.render('planMermaid', definition);
    container.innerHTML = svg;
    // Auto-fit: scale to fit container height
    var svgEl = container.querySelector('svg');
    if (svgEl) {
      var containerHeight = 380; // 400px max-height minus padding
      var svgHeight = svgEl.getBoundingClientRect().height || svgEl.getAttribute('height') || containerHeight;
      if (typeof svgHeight === 'string') svgHeight = parseFloat(svgHeight);
      if (svgHeight > containerHeight) {
        diagramScale = Math.max(0.3, containerHeight / svgHeight);
      } else {
        diagramScale = 1;
      }
      svgEl.style.transform = 'scale(' + diagramScale + ')';
      svgEl.style.transformOrigin = 'top left';
    }
    var label = document.getElementById('diagramZoomLevel');
    if (label) label.textContent = Math.round(diagramScale * 100) + '%';
  } catch (e) {
    console.error('Mermaid render failed:', e);
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">' + t('plan.diagramRenderFailed') + '</div>';
  }
}

// ═══════════════════════════════════════════════
//  DIAGRAM FULLSCREEN OVERLAY
// ═══════════════════════════════════════════════

var _overlayZoom = 100;

function expandDiagram(containerId) {
  var source = document.getElementById(containerId);
  if (!source) return;

  var overlay = document.getElementById('diagramOverlay');
  var body = document.getElementById('diagramOverlayBody');
  body.innerHTML = '';

  if (containerId === 'planDiagram') {
    var definition = buildMermaidDiagram('TD');
    if (definition) {
      var wrapper = document.createElement('div');
      wrapper.className = 'diagram-overlay-diagram';
      wrapper.style.cssText = 'width: 100%; overflow: visible; cursor: grab;';
      body.appendChild(wrapper);

      mermaid.render('overlayPlanMermaid', definition).then(function(result) {
        wrapper.innerHTML = result.svg;
        _overlayZoom = 100;
        _applyOverlayZoom();
      });

      overlay.style.display = 'flex';
      return;
    }
  }

  var sections = source.querySelectorAll('.diagram-section');
  if (sections.length > 0) {
    // Multi-diagram: re-render each
    var titles = source.querySelectorAll('.diagram-subtitle');
    var promises = [];
    sections.forEach(function(section, i) {
      if (titles[i]) {
        body.appendChild(titles[i].cloneNode(true));
      }
      var wrapper = document.createElement('div');
      wrapper.className = 'diagram-overlay-diagram';
      wrapper.style.cssText = 'width: 100%; overflow: visible; cursor: grab;';
      body.appendChild(wrapper);

      // Get the original mermaid source from the section's data attribute or re-extract
      var origSvg = section.querySelector('svg');
      if (origSvg) {
        var clone = origSvg.cloneNode(true);
        // Give unique IDs to avoid conflicts
        var newId = 'overlay_' + containerId + '_' + i;
        _deduplicateSvgIds(clone, newId);
        wrapper.appendChild(clone);
      }
    });
  } else {
    // Single diagram
    var svg = source.querySelector('svg');
    if (svg) {
      var wrapper = document.createElement('div');
      wrapper.className = 'diagram-overlay-diagram';
      wrapper.style.cssText = 'width: 100%; overflow: visible; cursor: grab;';
      var clone = svg.cloneNode(true);
      _deduplicateSvgIds(clone, 'overlay_' + containerId);
      wrapper.appendChild(clone);
      body.appendChild(wrapper);
    }
  }

  _overlayZoom = 100;
  _applyOverlayZoom();
  overlay.style.display = 'flex';
}

function _deduplicateSvgIds(svgEl, prefix) {
  // Replace all id attributes and their references within the SVG
  var allIds = svgEl.querySelectorAll('[id]');
  var idMap = {};
  allIds.forEach(function(el) {
    var oldId = el.getAttribute('id');
    var newId = prefix + '_' + oldId;
    idMap[oldId] = newId;
    el.setAttribute('id', newId);
  });

  // Update all url(#...) references in the SVG
  var svgHtml = svgEl.innerHTML;
  Object.keys(idMap).forEach(function(oldId) {
    // Replace url(#oldId) with url(#newId)
    svgHtml = svgHtml.split('url(#' + oldId + ')').join('url(#' + idMap[oldId] + ')');
    // Replace href="#oldId" with href="#newId"
    svgHtml = svgHtml.split('href="#' + oldId + '"').join('href="#' + idMap[oldId] + '"');
    svgHtml = svgHtml.split("href='#" + oldId + "'").join("href='#" + idMap[oldId] + "'");
  });
  svgEl.innerHTML = svgHtml;

  // Fix style tags — they reference IDs
  var styles = svgEl.querySelectorAll('style');
  styles.forEach(function(styleEl) {
    var css = styleEl.textContent;
    Object.keys(idMap).forEach(function(oldId) {
      css = css.split('#' + oldId).join('#' + idMap[oldId]);
    });
    styleEl.textContent = css;
  });
}

function closeDiagramOverlay(e) {
  if (e && e.target !== document.getElementById('diagramOverlay')) return;
  document.getElementById('diagramOverlay').style.display = 'none';
}

function overlayZoom(delta) {
  _overlayZoom = Math.max(25, Math.min(400, _overlayZoom + delta * 25));
  _applyOverlayZoom();
}

function _applyOverlayZoom() {
  var body = document.getElementById('diagramOverlayBody');
  body.querySelectorAll('svg').forEach(function(svg) {
    svg.style.transform = 'scale(' + (_overlayZoom / 100) + ')';
    svg.style.transformOrigin = 'top left';
  });
  document.getElementById('overlayZoomLevel').textContent = _overlayZoom + '%';
}

function renderPlan() {
  const container = document.getElementById('planContent');
  container.innerHTML = '';

  renderSystemDiagram();
  renderMermaidDiagram();

  // Render plan description
  if (PLAN_DATA.description) {
    var descDiv = document.createElement('div');
    descDiv.className = 'plan-description';
    descDiv.style.cssText = 'padding: 12px 16px; margin-bottom: 12px; background: var(--bg-secondary); border-radius: 6px; border-left: 3px solid var(--accent); font-size: 0.85rem; line-height: 1.5; color: var(--text-secondary); white-space: pre-wrap;';
    descDiv.textContent = PLAN_DATA.description;
    container.appendChild(descDiv);
  }

  var items = PLAN_DATA.execution || PLAN_DATA.groups || [];

  // Plan-level comment icon
  if (items.length > 0) {
    var planHeader = document.createElement('div');
    planHeader.style.cssText = 'text-align: right; margin-bottom: 8px;';
    planHeader.innerHTML = renderCommentIcon('plan', t('plan.entirePlan'));
    container.appendChild(planHeader);
  }

  items.forEach(function(item, itemIndex) {
    var tasks = item.tasks || [];
    var done = tasks.filter(function(t) { return t.status === 'done'; }).length;
    var total = tasks.length;

    var groupDiv = document.createElement('div');
    groupDiv.className = 'plan-group';

    var headerHtml = '<div class="plan-group-header">';
    if (item.id) {
      var isCurrent = state.phase && state.phase.startsWith(item.id + '.');
      headerHtml += '<span class="badge badge-' + (isCurrent ? 'warning' : 'info') + '">' + item.id + '</span> ';
    }
    headerHtml += '<span>' + escapeHtml(item.name || t('plan.group')) + '</span>';
    if (item.mode) headerHtml += ' <span class="badge badge-info">' + escapeHtml(item.mode) + '</span>';
    headerHtml += '<span class="plan-group-progress">' + t('plan.progress', {done: done, total: total}) + '</span>';
    var subphaseComment = t('plan.subPhaseComment', {id: item.id || '', name: item.name || ''});
    headerHtml += renderCommentIcon('plan', subphaseComment);
    headerHtml += '</div>';

    var itemScope = (LOCK_DATA.scope || {})[item.id];
    if (itemScope) {
      var scopeHtml = '<div style="padding: 4px 12px 8px; font-size: 0.75rem; color: var(--text-muted);">';
      var must = itemScope.must || [];
      var may = itemScope.may || [];
      if (must.length) scopeHtml += must.map(function(s) { return '<span style="color: var(--danger);">◆</span> ' + escapeHtml(s); }).join(' &nbsp; ');
      if (may.length) scopeHtml += (must.length ? ' &nbsp; ' : '') + may.map(function(s) { return '<span style="color: var(--text-muted);">◇</span> ' + escapeHtml(s); }).join(' &nbsp; ');
      scopeHtml += '</div>';
      headerHtml += scopeHtml;
    }

    groupDiv.innerHTML = headerHtml;

    tasks.forEach(function(task) {
      var taskDiv = document.createElement('div');
      taskDiv.className = 'plan-task';

      var commentTarget = 'Task: ' + task.title;

      var headerLine = document.createElement('div');
      headerLine.className = 'plan-task-header';
      headerLine.innerHTML = '<span class="plan-task-dot ' + (task.status || '').replace(/[^a-z0-9-]/gi, '') + '"></span>' +
        '<span class="plan-task-title">' + escapeHtml(task.title) + '</span>' +
        (task.agent ? ' <span class="badge badge-info" style="font-size: 0.65rem;">' + escapeHtml(task.agent) + '</span>' : '') +
        renderCommentIcon('plan', commentTarget);
      headerLine.onclick = function(e) {
        if (e.target.closest('.comment-icon')) return;
        taskDiv.classList.toggle('expanded');
      };
      taskDiv.appendChild(headerLine);

      var detail = document.createElement('div');
      detail.className = 'plan-task-detail';
      var detailHtml = '';
      if (task.description) detailHtml += '<div class="plan-task-description">' + escapeHtml(task.description) + '</div>';
      if (task.files && task.files.length > 0) detailHtml += '<div class="plan-task-files">' + task.files.map(escapeHtml).join(', ') + '</div>';
      detail.innerHTML = detailHtml;
      taskDiv.appendChild(detail);

      groupDiv.appendChild(taskDiv);
    });

    container.appendChild(groupDiv);
  });
}
