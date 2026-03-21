// ═══════════════════════════════════════════════
//  SCOPE RENDER
// ═══════════════════════════════════════════════
var _selectedScopeTab = null; // null = auto-detect, "all" = merged, or "3.1", "3.2", etc.

function _isExecutionPhase() {
  return LOCK_DATA.phase && LOCK_DATA.phase.match(/^3\.|^4\./);
}

function _hasPlanScopes() {
  return Object.keys(LOCK_DATA.scope || {}).length > 0;
}

function _getSubPhaseScope(subId) {
  return (LOCK_DATA.scope || {})[subId] || null;
}

function _getDisplayScope() {
  var scopeMap = LOCK_DATA.scope || {};
  if (_selectedScopeTab && _selectedScopeTab !== 'all') {
    return scopeMap[_selectedScopeTab] || { must: [], may: [] };
  }
  if (_selectedScopeTab !== 'all' && _isExecutionPhase()) {
    var parts = (LOCK_DATA.phase || '').split('.');
    var subKey = parts.length >= 2 ? parts[0] + '.' + parts[1] : LOCK_DATA.phase;
    return scopeMap[subKey] || { must: [], may: [] };
  }
  var merged = { must: [], may: [] };
  Object.keys(scopeMap).forEach(function(key) {
    var ps = scopeMap[key];
    if (ps.must) merged.must = merged.must.concat(ps.must);
    if (ps.may) merged.may = merged.may.concat(ps.may);
  });
  return merged;
}

function _getCurrentSubPhaseId() {
  if (!LOCK_DATA.phase) return null;
  var match = LOCK_DATA.phase.match(/^3\.(\d+)/);
  return match ? '3.' + match[1] : null;
}

function selectScopeTab(tabId) {
  _selectedScopeTab = (_selectedScopeTab === tabId) ? null : tabId;
  renderScope();
}

function renderScopeSubTabs() {
  var container = document.getElementById('scopeSubTabs');
  if (!container) return;
  container.innerHTML = '';
  var scopeMap = LOCK_DATA.scope || {};
  var keys = Object.keys(scopeMap).sort();
  if (keys.length <= 1) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'flex';

  // "All" tab
  var allBtn = document.createElement('button');
  allBtn.className = 'scope-sub-tab' + (_selectedScopeTab === 'all' || !_selectedScopeTab ? ' active' : '');
  allBtn.textContent = t('scope.all');
  allBtn.onclick = function() { _selectedScopeTab = 'all'; renderScope(); };
  container.appendChild(allBtn);

  // Per-phase tabs
  keys.forEach(function(key) {
    var btn = document.createElement('button');
    var isSelected = _selectedScopeTab === key;
    btn.className = 'scope-sub-tab' + (isSelected ? ' active' : '');
    var name = key;
    if (PLAN_DATA && PLAN_DATA.execution) {
      for (var i = 0; i < PLAN_DATA.execution.length; i++) {
        if (PLAN_DATA.execution[i].id === key) {
          name = key + ' — ' + PLAN_DATA.execution[i].name;
          break;
        }
      }
    }
    btn.textContent = name;
    btn.onclick = function() { _selectedScopeTab = key; renderScope(); };
    container.appendChild(btn);
  });
}

function renderScope() {
  renderScopeSubTabs();

  // On first render, default to merged view so "All" tab matches behavior
  if (_selectedScopeTab === null) _selectedScopeTab = 'all';

  var displayScope = _getDisplayScope();

  if (_hasPlanScopes()) {
    var scopeCard = document.getElementById('scopeMust');
    if (scopeCard) {
      var card = scopeCard.closest('.card');
      if (card) card.classList.remove('collapsed');
    }
  }
  var isMergedView = !_selectedScopeTab && !_isExecutionPhase() && _hasPlanScopes();
  var readOnly = isMergedView;

  const renderList = (list, elId, cls, scopeKey) => {
    const el = document.getElementById(elId);
    el.innerHTML = '';

    list.forEach((path, index) => {
      var commentTarget = scopeKey + ': ' + path;
      const li = document.createElement('li');
      li.className = `scope-item scope-${cls}`;
      li.innerHTML = `
        <span class="scope-icon">${cls === 'may' ? '◇' : '◆'}</span>
        <span class="scope-path">${path}</span>
        ${renderCommentIcon('scope', commentTarget)}
        ${readOnly ? '' : '<button class="scope-remove" onclick="removeScopeEntry(\'' + scopeKey + '\', ' + index + ')" title="Remove">✕</button>'}
      `;
      el.appendChild(li);
    });
  };
  renderList(displayScope.must || [], 'scopeMust', 'must', 'must');
  renderList(displayScope.may || [], 'scopeMay', 'may', 'may');

  // Hide add buttons in merged view (can't edit merged scope)
  document.querySelectorAll('.scope-add-btn').forEach(function(btn) {
    btn.style.display = readOnly ? 'none' : '';
  });

  // Update title
  var titleEl = document.getElementById('scopeTitle');
  if (titleEl) {
    if (_selectedScopeTab) {
      titleEl.textContent = t('scope.scopeTab', {id: _selectedScopeTab});
    } else if (readOnly) {
      titleEl.textContent = t('scope.contractMerged');
    } else {
      titleEl.textContent = t('scope.contract');
    }
  }
}

function removeScopeEntry(key, index) {
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  var phaseKey = _selectedScopeTab;
  if (!phaseKey) return; // Can't edit merged view
  var scopeMap = LOCK_DATA.scope || {};
  if (scopeMap[phaseKey] && scopeMap[phaseKey][key]) {
    scopeMap[phaseKey][key].splice(index, 1);
    apiSetScope(ctx.projectId, ctx.branch, LOCK_DATA.scope).then(function() { renderScope(); });
  }
}

function addScopeEntry(key) {
  var phaseKey = _selectedScopeTab;
  if (!phaseKey) {
    showToast(t('scope.selectPhaseTab'));
    return;
  }
  const inputId = `scopeInput_${key}`;
  const existing = document.getElementById(inputId);
  if (existing) { existing.focus(); return; }

  const container = document.getElementById(key === 'may' ? 'scopeMay' : 'scopeMust');
  const inputLi = document.createElement('li');
  inputLi.className = 'scope-item scope-add-input';
  inputLi.innerHTML = `<input type="text" id="${inputId}" class="scope-input-field" placeholder="${t('placeholders.scopePath')}" onkeydown="handleScopeInput(event, '${key}')">`;
  container.appendChild(inputLi);
  document.getElementById(inputId).focus();
}

function handleScopeInput(event, key) {
  if (event.key === 'Escape') {
    renderScope();
    return;
  }
  if (event.key !== 'Enter') return;
  var value = event.target.value.trim();
  if (!value) return;
  var ctx = getWorkspaceContext();
  if (!ctx) return;
  var phaseKey = _selectedScopeTab;
  if (!phaseKey) return;
  var scopeMap = LOCK_DATA.scope || {};
  if (!scopeMap[phaseKey]) scopeMap[phaseKey] = { must: [], may: [] };
  if (!scopeMap[phaseKey][key]) scopeMap[phaseKey][key] = [];
  scopeMap[phaseKey][key].push(value);
  event.target.value = '';
  apiSetScope(ctx.projectId, ctx.branch, LOCK_DATA.scope).then(function() { renderScope(); });
}

EventBus.on('state:refreshed', renderScope);
