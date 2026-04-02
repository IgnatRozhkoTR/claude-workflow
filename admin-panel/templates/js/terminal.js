// ═══════════════════════════════════════════════
//  TERMINAL
// ═══════════════════════════════════════════════
var term = null;
var fitAddon = null;
var terminalWs = null;
var terminalConnected = false;

function _getActiveTerminalKind() {
  return typeof ACTIVE_TERMINAL_KIND === 'string' && ACTIVE_TERMINAL_KIND ? ACTIVE_TERMINAL_KIND : 'claude';
}

function _buildTerminalWsUrl(projectId, branch) {
  var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  var base = protocol + '//' + window.location.host + '/ws/terminal/' +
             encodeURIComponent(projectId) + '/' + encodeURIComponent(branch);
  var kind = _getActiveTerminalKind();
  return kind && kind !== 'claude' ? base + '/' + encodeURIComponent(kind) : base;
}

var TERMINAL_THEMES = {
  dark: {
    background: '#1a1a2e',
    foreground: '#e0e0e0',
    cursor: '#e0e0e0',
    cursorAccent: '#1a1a2e',
    selectionBackground: 'rgba(255, 255, 255, 0.15)',
    black: '#2a2a3e',
    red: '#ff6b6b',
    green: '#51cf66',
    yellow: '#ffd43b',
    blue: '#818cf8',
    magenta: '#da77f2',
    cyan: '#22d3ee',
    white: '#e0e0e0',
    brightBlack: '#6b7280',
    brightRed: '#ff8787',
    brightGreen: '#69db7c',
    brightYellow: '#ffe066',
    brightBlue: '#a5b4fc',
    brightMagenta: '#e599f7',
    brightCyan: '#67e8f9',
    brightWhite: '#ffffff'
  },
  light: {
    background: '#faf8f5',
    foreground: '#2c2c2c',
    cursor: '#2c2c2c',
    cursorAccent: '#faf8f5',
    selectionBackground: 'rgba(0, 0, 0, 0.1)',
    black: '#2c2c2c',
    red: '#c92a2a',
    green: '#2b8a3e',
    yellow: '#e67700',
    blue: '#1864ab',
    magenta: '#862e9c',
    cyan: '#0c8599',
    white: '#faf8f5',
    brightBlack: '#868e96',
    brightRed: '#e03131',
    brightGreen: '#37b24d',
    brightYellow: '#f59f00',
    brightBlue: '#1c7ed6',
    brightMagenta: '#9c36b5',
    brightCyan: '#1098ad',
    brightWhite: '#ffffff'
  }
};

function getTerminalTheme() {
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  return isDark ? TERMINAL_THEMES.dark : TERMINAL_THEMES.light;
}

function _createTerminal(containerId, wsRef) {
  var container = document.getElementById(containerId);
  if (!container) return null;

  var terminal = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace",
    theme: getTerminalTheme(),
    allowProposedApi: true,
    scrollback: 5000,
    copyOnSelect: true
  });

  var addon = new FitAddon.FitAddon();
  terminal.loadAddon(addon);

  var webLinksAddon = new WebLinksAddon.WebLinksAddon();
  terminal.loadAddon(webLinksAddon);

  terminal.open(container);
  addon.fit();

  terminal.attachCustomKeyEventHandler(function(e) {
    if (e.type !== 'keydown') return true;
    var isMacCopy = e.metaKey && !e.ctrlKey && e.key === 'c';
    var isCtrlShiftCopy = e.ctrlKey && e.shiftKey && e.key === 'C';
    if ((isMacCopy || isCtrlShiftCopy) && terminal.hasSelection()) {
      var selected = terminal.getSelection();
      if (selected && typeof safeCopyToClipboard === 'function') {
        safeCopyToClipboard(selected);
      }
      return false;
    }
    return true;
  });

  if (terminal.parser) {
    terminal.parser.registerOscHandler(52, function(data) {
      var parts = data.split(';');
      if (parts.length >= 2) {
        try {
          var decoded = atob(parts[parts.length - 1]);
          if (typeof safeCopyToClipboard === 'function') {
            safeCopyToClipboard(decoded);
          }
        } catch(e) {}
      }
      return true;
    });
  }

  container.addEventListener('wheel', function(e) {
    e.stopPropagation();
  }, { passive: true });

  container.addEventListener('paste', function(e) {
    var ws = wsRef();
    if (ws && ws.readyState === WebSocket.OPEN) {
      var text = (e.clipboardData || window.clipboardData).getData('text');
      if (text) ws.send(text);
    }
    e.preventDefault();
  });

  terminal.onData(function(data) {
    var ws = wsRef();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  });

  terminal.onResize(function(size) {
    var ws = wsRef();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ resize: [size.cols, size.rows] }));
    }
  });

  return { terminal: terminal, fitAddon: addon };
}

function _connectTerminal(terminal, addon, wsUrl, options) {
  var ws = new WebSocket(wsUrl);

  ws.onopen = function() {
    options.onConnected();
    terminal.clear();
    if (addon) {
      addon.fit();
      if (options.focusOnOpen) terminal.focus();
      var dims = addon.proposeDimensions();
      if (dims) {
        ws.send(JSON.stringify({ resize: [dims.cols, dims.rows] }));
      }
    }
  };

  ws.onmessage = function(event) {
    if (typeof event.data === 'string' && event.data.startsWith('{')) {
      try {
        var msg = JSON.parse(event.data);
        if (msg.error) {
          terminal.writeln('\r\n\x1b[31m' + msg.error + '\x1b[0m');
          options.onError();
          return;
        }
      } catch(e) {}
    }
    terminal.write(event.data);
  };

  ws.onclose = function() {
    options.onDisconnected();
  };

  ws.onerror = function() {
    options.onError();
  };

  return ws;
}

function initTerminal() {
  if (term) return;

  var result = _createTerminal('terminalContainer', function() { return terminalWs; });
  if (!result) return;

  term = result.terminal;
  fitAddon = result.fitAddon;

  window.addEventListener('resize', function() {
    if (fitAddon && document.getElementById('panel-terminal').classList.contains('active')) {
      fitAddon.fit();
    }
    if (splitFitAddon && document.getElementById('splitContainer') &&
        document.getElementById('splitContainer').classList.contains('split-active')) {
      splitFitAddon.fit();
    }
  });

  term.writeln('Terminal ready. Click Connect or use Start/Resume.');
}

function connectTerminal() {
  if (!term) {
    initTerminal();
  }

  var ctx = getWorkspaceContext();
  if (!ctx) {
    if (term) term.writeln('\r\n\x1b[31mNo workspace selected.\x1b[0m');
    return;
  }

  if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
    return;
  }

  var wsUrl = _buildTerminalWsUrl(ctx.projectId, ctx.branch);

  updateTerminalStatus('connecting');
  if (term) term.writeln('\r\nConnecting to tmux session...');

  terminalWs = _connectTerminal(term, fitAddon, wsUrl, {
    focusOnOpen: true,
    onConnected: function() {
      terminalConnected = true;
      updateTerminalStatus('connected');
    },
    onDisconnected: function() {
      terminalConnected = false;
      updateTerminalStatus('disconnected');
      if (term) term.writeln('\r\n\x1b[33mDisconnected from terminal.\x1b[0m');
    },
    onError: function() {
      terminalConnected = false;
      updateTerminalStatus('error');
      if (term) term.writeln('\r\n\x1b[31mWebSocket error. Is the tmux session running?\x1b[0m');
    }
  });
}

function disconnectTerminal() {
  if (terminalWs) {
    terminalWs.close();
    terminalWs = null;
  }
  terminalConnected = false;
  updateTerminalStatus('disconnected');
}

function killTerminalSession() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  disconnectTerminal();

  apiPost('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/terminal/kill', {
    kind: _getActiveTerminalKind()
  })
  .then(function() {
    if (term) term.writeln('\r\n\x1b[33mSession killed.\x1b[0m');
    loadTerminalSessions();
  })
  .catch(function(e) {
    if (term) term.writeln('\r\n\x1b[31mKill failed: ' + e.message + '\x1b[0m');
  });
}

function updateTerminalStatus(status) {
  var el = document.getElementById('terminalStatus');
  var connectBtn = document.getElementById('terminalConnectBtn');
  var disconnectBtn = document.getElementById('terminalDisconnectBtn');
  var killBtn = document.getElementById('terminalKillBtn');

  if (el) {
    switch(status) {
      case 'connected':
        el.textContent = t('terminal.connected');
        el.className = 'terminal-status connected';
        break;
      case 'connecting':
        el.textContent = t('terminal.connecting');
        el.className = 'terminal-status';
        break;
      case 'error':
        el.textContent = t('terminal.error');
        el.className = 'terminal-status';
        break;
      default:
        el.textContent = t('terminal.disconnected');
        el.className = 'terminal-status';
    }
  }

  if (connectBtn) connectBtn.style.display = (status === 'connected') ? 'none' : '';
  if (disconnectBtn) disconnectBtn.style.display = (status === 'connected') ? '' : 'none';
  if (killBtn) killBtn.style.display = (status === 'connected') ? '' : 'none';
}

function updateTerminalTheme() {
  if (term) {
    term.options.theme = getTerminalTheme();
  }
  if (splitTerm) {
    splitTerm.options.theme = getTerminalTheme();
  }
}

function onTerminalTabActivated() {
  if (!term) {
    initTerminal();
  }
  if (fitAddon) {
    setTimeout(function() { fitAddon.fit(); if (term) term.focus(); }, 50);
  }
  startSessionListPolling();
}

// ═══════════════════════════════════════════════
//  SESSION LIST
// ═══════════════════════════════════════════════
var _sessionListInterval = null;

function loadTerminalSessions() {
  apiGet('/api/terminal/sessions')
    .then(function(sessions) {
      renderSessionList(sessions);
    })
    .catch(function() {
      renderSessionList([]);
    });
}

function renderSessionList(sessions) {
  var container = document.getElementById('terminalSessionList');
  if (!container) return;

  if (!sessions.length) {
    container.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">' + t('terminal.noSessions') + '</span>';
    return;
  }

  var html = '';
  sessions.forEach(function(s) {
    var statusClass = s.attached ? 'session-attached' : 'session-detached';
    var statusText = s.attached ? t('terminal.attached') : t('terminal.detached');
    html += '<div class="session-item" title="' + escapeHtml(s.command || s.name) + '">' +
      '<span class="session-status-dot ' + statusClass + '"></span>' +
      '<span class="session-name">' + escapeHtml(s.name) + '</span>' +
      '<span class="session-status-label">' + statusText + '</span>' +
      '<button class="session-kill-btn" onclick="killSessionByName(\'' + escapeAttr(s.name) + '\')" title="' + t('terminal.killSession') + '">&times;</button>' +
      '</div>';
  });
  container.innerHTML = html;
}

function killSessionByName(name) {
  apiPost('/api/terminal/sessions/' + encodeURIComponent(name) + '/kill', {})
    .then(function() { loadTerminalSessions(); })
    .catch(function() {});
}

function startSessionListPolling() {
  loadTerminalSessions();
  if (_sessionListInterval) clearInterval(_sessionListInterval);
  _sessionListInterval = setInterval(loadTerminalSessions, 5000);
}

function stopSessionListPolling() {
  if (_sessionListInterval) {
    clearInterval(_sessionListInterval);
    _sessionListInterval = null;
  }
}

// ═══════════════════════════════════════════════
//  SPLIT TERMINAL
// ═══════════════════════════════════════════════
var splitTerm = null;
var splitFitAddon = null;
var splitWs = null;
var splitConnected = false;

function toggleSplitTerminal() {
  var container = document.getElementById('splitContainer');
  var btn = document.getElementById('splitTerminalBtn');
  if (!container) return;

  var isActive = container.classList.contains('split-active');

  if (isActive) {
    container.classList.remove('split-active');
    if (btn) btn.classList.remove('active');
    disconnectSplitTerminal();
  } else {
    container.classList.add('split-active');
    if (btn) btn.classList.add('active');

    if (!splitTerm) {
      initSplitTerminal();
    }

    if (splitFitAddon) {
      setTimeout(function() { splitFitAddon.fit(); }, 100);
      setTimeout(function() {
        if (splitTerm) splitTerm.focus();
      }, 150);
    }

    connectSplitTerminal();
  }
}

function initSplitTerminal() {
  if (splitTerm) return;

  var result = _createTerminal('splitTerminalContainer', function() { return splitWs; });
  if (!result) return;

  splitTerm = result.terminal;
  splitFitAddon = result.fitAddon;
}

function connectSplitTerminal() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  if (splitWs && splitWs.readyState === WebSocket.OPEN) return;

  var wsUrl = _buildTerminalWsUrl(ctx.projectId, ctx.branch);

  updateSplitTerminalStatus('connecting');

  splitWs = _connectTerminal(splitTerm, splitFitAddon, wsUrl, {
    focusOnOpen: true,
    onConnected: function() {
      splitConnected = true;
      updateSplitTerminalStatus('connected');
    },
    onDisconnected: function() {
      splitConnected = false;
      updateSplitTerminalStatus('disconnected');
    },
    onError: function() {
      splitConnected = false;
      updateSplitTerminalStatus('error');
    }
  });
}

function disconnectSplitTerminal() {
  if (splitWs) {
    splitWs.close();
    splitWs = null;
  }
  splitConnected = false;
  updateSplitTerminalStatus('disconnected');
}

function updateSplitTerminalStatus(status) {
  var el = document.getElementById('splitTerminalStatus');
  var connectBtn = document.getElementById('splitConnectBtn');
  var disconnectBtn = document.getElementById('splitDisconnectBtn');

  if (el) {
    switch(status) {
      case 'connected':
        el.textContent = t('terminal.connected');
        el.className = 'terminal-status connected';
        break;
      case 'connecting':
        el.textContent = t('terminal.connecting');
        el.className = 'terminal-status';
        break;
      default:
        el.textContent = t('terminal.disconnected');
        el.className = 'terminal-status';
    }
  }

  if (connectBtn) connectBtn.style.display = (status === 'connected') ? 'none' : '';
  if (disconnectBtn) disconnectBtn.style.display = (status === 'connected') ? '' : 'none';
}

// Drag-to-resize split panel
(function() {
  var handle = null;
  var startX = 0;
  var startWidth = 0;

  document.addEventListener('mousedown', function(e) {
    if (e.target.id === 'splitHandle') {
      handle = e.target;
      startX = e.clientX;
      var splitTermEl = document.getElementById('splitTerminal');
      startWidth = splitTermEl ? splitTermEl.offsetWidth : 400;
      handle.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    }
  });

  document.addEventListener('mousemove', function(e) {
    if (!handle) return;
    var diff = startX - e.clientX;
    var newWidth = Math.max(300, Math.min(startWidth + diff, window.innerWidth - 400));
    var splitTermEl = document.getElementById('splitTerminal');
    if (splitTermEl) {
      splitTermEl.style.width = newWidth + 'px';
      splitTermEl.style.flex = 'none';
    }
    if (splitFitAddon) splitFitAddon.fit();
    if (fitAddon && document.getElementById('panel-terminal').classList.contains('active')) fitAddon.fit();
  });

  document.addEventListener('mouseup', function() {
    if (handle) {
      handle.classList.remove('dragging');
      handle = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
})();

document.addEventListener('workspace-reset', function() {
  if (typeof disconnectTerminal === 'function') disconnectTerminal();
  if (typeof disconnectSplitTerminal === 'function') disconnectSplitTerminal();
  if (term) { term.clear(); term.dispose(); term = null; fitAddon = null; }
  if (typeof splitTerm !== 'undefined' && splitTerm) { splitTerm.clear(); splitTerm.dispose(); splitTerm = null; splitFitAddon = null; }
  terminalConnected = false;
});
