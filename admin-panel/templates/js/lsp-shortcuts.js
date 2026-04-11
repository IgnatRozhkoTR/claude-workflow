// ===============================================
//  LSP KEYBOARD SHORTCUTS
// ===============================================

var _lspIsMac = navigator.platform.indexOf('Mac') > -1;
var LSP_DEFAULT_SHORTCUTS = {
  goToDefinition: _lspIsMac ? 'Cmd+B' : 'Ctrl+B',
  findReferences: _lspIsMac ? 'Cmd+Alt+B' : 'Ctrl+Alt+B',
  peekDefinition: 'Alt+F12',
  showHover: _lspIsMac ? 'Cmd+K' : 'Ctrl+K'
};

var LSP_SHORTCUT_LABELS = {
  goToDefinition: 'Go to Definition',
  findReferences: 'Find All References',
  peekDefinition: 'Peek Definition',
  showHover: 'Show Hover Info'
};

var _LSP_ACTION_MAP = {
  goToDefinition: 'editor.action.revealDefinition',
  findReferences: 'editor.action.referenceSearch.trigger',
  peekDefinition: 'editor.action.peekDefinition',
  showHover: 'editor.action.showHover'
};

var _LSP_DEFAULT_KEYBINDINGS = {
  goToDefinition: 'F12',
  findReferences: 'Shift+F12',
  peekDefinition: 'Alt+F12',
  showHover: 'Cmd+K'
};

// --- Shortcut parsing ---

function parseLspShortcut(shortcutStr) {
  if (!shortcutStr || typeof shortcutStr !== 'string') return 0;
  if (typeof monaco === 'undefined') return 0;

  var parts = shortcutStr.split('+').map(function(s) { return s.trim(); });
  var result = 0;

  for (var i = 0; i < parts.length; i++) {
    var part = parts[i];
    var lower = part.toLowerCase();
    var code = _resolveKeyPart(lower, part);
    if (code === -1) return 0;
    result = result | code;
  }

  return result;
}

function _resolveKeyPart(lower, original) {
  if (typeof monaco === 'undefined') return -1;

  if (lower === 'cmd' || lower === 'meta' || lower === 'command') {
    return monaco.KeyMod.CtrlCmd;
  }
  if (lower === 'ctrl' || lower === 'control') {
    return monaco.KeyMod.CtrlCmd;
  }
  if (lower === 'alt' || lower === 'option' || lower === 'opt') {
    return monaco.KeyMod.Alt;
  }
  if (lower === 'shift') {
    return monaco.KeyMod.Shift;
  }

  if (/^[a-z]$/.test(lower)) {
    var keyName = 'Key' + lower.toUpperCase();
    return monaco.KeyCode[keyName] != null ? monaco.KeyCode[keyName] : -1;
  }

  var fMatch = lower.match(/^f(\d{1,2})$/);
  if (fMatch) {
    var fNum = parseInt(fMatch[1], 10);
    if (fNum >= 1 && fNum <= 12) {
      return monaco.KeyCode['F' + fNum] != null ? monaco.KeyCode['F' + fNum] : -1;
    }
    return -1;
  }

  var specialKeys = {
    enter: 'Enter',
    return: 'Enter',
    escape: 'Escape',
    esc: 'Escape',
    tab: 'Tab',
    space: 'Space',
    backspace: 'Backspace',
    delete: 'Delete',
    insert: 'Insert',
    home: 'Home',
    end: 'End',
    pageup: 'PageUp',
    pagedown: 'PageDown',
    up: 'UpArrow',
    down: 'DownArrow',
    left: 'LeftArrow',
    right: 'RightArrow',
    arrowup: 'UpArrow',
    arrowdown: 'DownArrow',
    arrowleft: 'LeftArrow',
    arrowright: 'RightArrow'
  };

  var mapped = specialKeys[lower];
  if (mapped) {
    return monaco.KeyCode[mapped] != null ? monaco.KeyCode[mapped] : -1;
  }

  return -1;
}

// --- Storage ---

function getLspShortcuts() {
  var stored = {};
  try {
    var raw = localStorage.getItem('lsp-shortcuts');
    if (raw) stored = JSON.parse(raw);
  } catch (e) {
    stored = {};
  }

  var merged = {};
  var actions = Object.keys(LSP_DEFAULT_SHORTCUTS);
  for (var i = 0; i < actions.length; i++) {
    var action = actions[i];
    merged[action] = (stored[action] != null && stored[action] !== '')
      ? stored[action]
      : LSP_DEFAULT_SHORTCUTS[action];
  }
  return merged;
}

function saveLspShortcuts(shortcuts) {
  localStorage.setItem('lsp-shortcuts', JSON.stringify(shortcuts));
}

// --- Apply to Monaco ---

function applyLspShortcuts() {
  if (typeof monaco === 'undefined') return;

  var shortcuts = getLspShortcuts();
  var actions = Object.keys(_LSP_ACTION_MAP);

  for (var i = 0; i < actions.length; i++) {
    var action = actions[i];
    var commandId = _LSP_ACTION_MAP[action];
    var defaultKey = _LSP_DEFAULT_KEYBINDINGS[action];

    var defaultKeybinding = parseLspShortcut(defaultKey);
    if (defaultKeybinding) {
      monaco.editor.addKeybindingRule({
        keybinding: defaultKeybinding,
        command: null
      });
    }

    var newKeybinding = parseLspShortcut(shortcuts[action]);
    if (newKeybinding) {
      monaco.editor.addKeybindingRule({
        keybinding: newKeybinding,
        command: commandId
      });
    }
  }
}

// --- Display formatting ---

function formatShortcutDisplay(shortcutStr) {
  if (!shortcutStr) return '';

  var parts = shortcutStr.split('+').map(function(s) { return s.trim(); });
  var formatted = parts.map(function(part) {
    var lower = part.toLowerCase();
    if (_lspIsMac) {
      if (lower === 'cmd' || lower === 'meta' || lower === 'command') return '\u2318';
      if (lower === 'alt' || lower === 'option' || lower === 'opt') return '\u2325';
      if (lower === 'shift') return '\u21E7';
      if (lower === 'ctrl' || lower === 'control') return '\u2303';
    }
    return part;
  });

  return formatted.join('+');
}

// --- Config panel rendering (dashboard card) ---

function renderLspShortcutsConfig() {
  var body = document.getElementById('lspShortcutsBody');
  if (!body) return;

  var shortcuts = getLspShortcuts();
  var actions = Object.keys(LSP_SHORTCUT_LABELS);

  var html = '';
  for (var i = 0; i < actions.length; i++) {
    var action = actions[i];
    var label = LSP_SHORTCUT_LABELS[action];
    var value = shortcuts[action] || '';
    html += '<div class="lsp-shortcut-row">'
      + '<label>' + label + '</label>'
      + '<input type="text" id="lsp-cfg-shortcut-' + action + '" value="' + _lspEscapeAttr(value) + '" placeholder="e.g., Cmd+B">'
      + '</div>';
  }

  html += '<div class="shortcut-hint">'
    + 'Available modifiers: Cmd (\u2318), Alt/Option (\u2325), Shift (\u21E7), Ctrl<br>'
    + 'Keys: A-Z, F1-F12, Enter, Escape, Tab, Space, arrows<br>'
    + 'Example: Cmd+B, Cmd+Alt+B, Shift+F12'
    + '</div>';

  html += '<div style="display: flex; justify-content: flex-end; margin-top: 10px;">'
    + '<button class="btn btn-sm" onclick="saveLspShortcutsFromConfig()">Save</button>'
    + '</div>';

  body.innerHTML = html;
}

function saveLspShortcutsFromConfig() {
  var shortcuts = {};
  var actions = Object.keys(LSP_SHORTCUT_LABELS);

  for (var i = 0; i < actions.length; i++) {
    var action = actions[i];
    var input = document.getElementById('lsp-cfg-shortcut-' + action);
    shortcuts[action] = input ? input.value.trim() : LSP_DEFAULT_SHORTCUTS[action];
  }

  saveLspShortcuts(shortcuts);

  window._monacoReady.then(function() {
    applyLspShortcuts();
  });

  if (typeof showToast === 'function') {
    showToast('LSP shortcuts saved');
  }
}

// --- Setup wizard rendering ---

function renderSetupShortcutsSection() {
  var shortcuts = getLspShortcuts();
  var actions = Object.keys(LSP_SHORTCUT_LABELS);

  var html = '';
  for (var i = 0; i < actions.length; i++) {
    var action = actions[i];
    var label = LSP_SHORTCUT_LABELS[action];
    var value = shortcuts[action] || '';
    html += '<div class="setup-shortcut-row">'
      + '<label>' + label + '</label>'
      + '<input type="text" id="shortcut-' + action + '" value="' + _lspEscapeAttr(value) + '" placeholder="e.g., Cmd+B">'
      + '</div>';
  }

  html += '<div class="shortcut-hint">'
    + 'Available modifiers: Cmd (\u2318), Alt/Option (\u2325), Shift (\u21E7), Ctrl<br>'
    + 'Keys: A-Z, F1-F12, Enter, Escape, Tab, Space, arrows<br>'
    + 'Example: Cmd+B, Cmd+Alt+B, Shift+F12'
    + '</div>';

  return html;
}

function collectSetupShortcuts() {
  var shortcuts = {};
  var actions = Object.keys(LSP_SHORTCUT_LABELS);

  for (var i = 0; i < actions.length; i++) {
    var action = actions[i];
    var input = document.getElementById('shortcut-' + action);
    shortcuts[action] = input ? input.value.trim() : LSP_DEFAULT_SHORTCUTS[action];
  }

  return shortcuts;
}

// --- Helpers ---

function _lspEscapeAttr(str) {
  return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
