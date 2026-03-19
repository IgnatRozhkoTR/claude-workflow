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
    black: '#1a1a2e',
    red: '#ff6b6b',
    green: '#51cf66',
    yellow: '#ffd43b',
    blue: '#748ffc',
    magenta: '#da77f2',
    cyan: '#66d9e8',
    white: '#e0e0e0',
    brightBlack: '#555',
    brightRed: '#ff8787',
    brightGreen: '#69db7c',
    brightYellow: '#ffe066',
    brightBlue: '#91a7ff',
    brightMagenta: '#e599f7',
    brightCyan: '#99e9f2',
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
  });

  term.writeln('Terminal ready. Click Connect or use Start/Resume.');
}

function connectTerminal() {
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
}

function onTerminalTabActivated() {
  if (!term) {
    initTerminal();
  }
  if (fitAddon) {
    setTimeout(function() { fitAddon.fit(); }, 50);
  }
}
