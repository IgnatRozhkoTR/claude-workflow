// ═══════════════════════════════════════════════
//  TERMINAL
// ═══════════════════════════════════════════════
var term = null;
var fitAddon = null;
var terminalWs = null;
var terminalConnected = false;

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

function initTerminal() {
  if (term) return;

  var container = document.getElementById('terminalContainer');
  if (!container) return;

  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace",
    theme: getTerminalTheme(),
    allowProposedApi: true,
    scrollback: 5000
  });

  fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);

  var webLinksAddon = new WebLinksAddon.WebLinksAddon();
  term.loadAddon(webLinksAddon);

  term.open(container);
  fitAddon.fit();

  container.addEventListener('wheel', function(e) {
    e.stopPropagation();
  }, { passive: true });

  term.onData(function(data) {
    if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
      terminalWs.send(data);
    }
  });

  term.onResize(function(size) {
    if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
      terminalWs.send(JSON.stringify({ resize: [size.cols, size.rows] }));
    }
  });

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

  var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = protocol + '//' + window.location.host + '/ws/terminal/' +
              encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch);

  updateTerminalStatus('connecting');
  if (term) term.writeln('\r\nConnecting to tmux session...');

  terminalWs = new WebSocket(wsUrl);

  terminalWs.onopen = function() {
    terminalConnected = true;
    updateTerminalStatus('connected');
    if (term) {
      term.clear();
      if (fitAddon) {
        fitAddon.fit();
        var dims = fitAddon.proposeDimensions();
        if (dims) {
          terminalWs.send(JSON.stringify({ resize: [dims.cols, dims.rows] }));
        }
      }
    }
  };

  terminalWs.onmessage = function(event) {
    if (term) {
      if (typeof event.data === 'string' && event.data.startsWith('{')) {
        try {
          var msg = JSON.parse(event.data);
          if (msg.error) {
            term.writeln('\r\n\x1b[31m' + msg.error + '\x1b[0m');
            updateTerminalStatus('error');
            return;
          }
        } catch(e) {}
      }
      term.write(event.data);
    }
  };

  terminalWs.onclose = function() {
    terminalConnected = false;
    updateTerminalStatus('disconnected');
    if (term) term.writeln('\r\n\x1b[33mDisconnected from terminal.\x1b[0m');
  };

  terminalWs.onerror = function() {
    terminalConnected = false;
    updateTerminalStatus('error');
    if (term) term.writeln('\r\n\x1b[31mWebSocket error. Is the tmux session running?\x1b[0m');
  };
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

  fetch('/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/terminal/kill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (term) term.writeln('\r\n\x1b[33mSession killed.\x1b[0m');
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
    setTimeout(function() { fitAddon.fit(); }, 50);
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
  var container = document.getElementById('splitTerminalContainer');
  if (!container || splitTerm) return;

  splitTerm = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace",
    theme: getTerminalTheme(),
    allowProposedApi: true,
    scrollback: 5000
  });

  splitFitAddon = new FitAddon.FitAddon();
  splitTerm.loadAddon(splitFitAddon);

  var webLinksAddon = new WebLinksAddon.WebLinksAddon();
  splitTerm.loadAddon(webLinksAddon);

  splitTerm.open(container);
  splitFitAddon.fit();

  splitTerm.onData(function(data) {
    if (splitWs && splitWs.readyState === WebSocket.OPEN) {
      splitWs.send(data);
    }
  });

  splitTerm.onResize(function(size) {
    if (splitWs && splitWs.readyState === WebSocket.OPEN) {
      splitWs.send(JSON.stringify({ resize: [size.cols, size.rows] }));
    }
  });

  container.addEventListener('wheel', function(e) {
    e.stopPropagation();
  }, { passive: true });
}

function connectSplitTerminal() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  if (splitWs && splitWs.readyState === WebSocket.OPEN) return;

  var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = protocol + '//' + window.location.host + '/ws/terminal/' +
              encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch);

  updateSplitTerminalStatus('connecting');

  splitWs = new WebSocket(wsUrl);

  splitWs.onopen = function() {
    splitConnected = true;
    updateSplitTerminalStatus('connected');
    if (splitTerm) splitTerm.clear();
    if (splitFitAddon) {
      splitFitAddon.fit();
      if (splitTerm) splitTerm.focus();
      var dims = splitFitAddon.proposeDimensions();
      if (dims) {
        splitWs.send(JSON.stringify({ resize: [dims.cols, dims.rows] }));
      }
    }
  };

  splitWs.onmessage = function(event) {
    if (splitTerm) {
      if (typeof event.data === 'string' && event.data.startsWith('{')) {
        try {
          var msg = JSON.parse(event.data);
          if (msg.error) {
            splitTerm.writeln('\r\n\x1b[31m' + msg.error + '\x1b[0m');
            updateSplitTerminalStatus('error');
            return;
          }
        } catch(e) {}
      }
      splitTerm.write(event.data);
    }
  };

  splitWs.onclose = function() {
    splitConnected = false;
    updateSplitTerminalStatus('disconnected');
  };

  splitWs.onerror = function() {
    splitConnected = false;
    updateSplitTerminalStatus('error');
  };
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
