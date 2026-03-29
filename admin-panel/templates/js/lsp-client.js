// ===============================================
//  LSP CLIENT (WebSocket bridge to backend LSP proxy)
// ===============================================

var _lspSocket = null;
var _lspConnected = false;
var _lspPendingRequests = {};
var _lspRequestId = 1;
var _lspOpenDocuments = {};
var _lspProviderDisposables = [];
var _lspReconnectTimer = null;
var _lspLanguageProfileMap = {};  // languageId -> profile_id

// --- Profile routing ---

function updateLspLanguageMap() {
  _lspLanguageProfileMap = {};
  if (typeof _lspProfiles !== 'undefined' && Array.isArray(_lspProfiles)) {
    _lspProfiles.forEach(function(p) {
      if (p.language && p.profile_id && p.instance_status === 'running') {
        _lspLanguageProfileMap[p.language] = p.profile_id;
      }
    });
  }
}

function getProfileIdForLanguage(languageId) {
  if (_lspLanguageProfileMap[languageId]) return _lspLanguageProfileMap[languageId];
  // Try common aliases
  var aliases = {
    javascript: 'typescript', jsx: 'typescript', tsx: 'typescript',
    javascriptreact: 'typescript', typescriptreact: 'typescript',
    py: 'python'
  };
  var mapped = aliases[languageId];
  if (mapped && _lspLanguageProfileMap[mapped]) return _lspLanguageProfileMap[mapped];
  return null;
}

// --- Connection management ---

function connectLsp() {
  var ctx = getWorkspaceContext();
  if (!ctx) return;

  disconnectLsp(true);

  var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  var host = window.location.host;
  var url = protocol + '//' + host + '/ws/lsp/'
    + encodeURIComponent(ctx.projectId) + '/'
    + encodeURIComponent(ctx.branch);

  var socket = new WebSocket(url);

  socket.onopen = function() {
    socket.send(JSON.stringify({ profile_id: null }));
    _lspConnected = true;
    _resendOpenDocuments();
  };

  socket.onmessage = function(event) {
    var msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      console.warn('LSP: failed to parse message', e);
      return;
    }
    _handleLspMessage(msg);
  };

  socket.onclose = function() {
    _lspConnected = false;
    _rejectAllPending('LSP connection closed');
    _scheduleReconnect();
  };

  socket.onerror = function(err) {
    console.warn('LSP: WebSocket error', err);
  };

  _lspSocket = socket;
}

function disconnectLsp(keepDocuments) {
  if (_lspReconnectTimer) {
    clearTimeout(_lspReconnectTimer);
    _lspReconnectTimer = null;
  }
  if (_lspSocket) {
    _lspSocket.onclose = null;
    _lspSocket.onerror = null;
    _lspSocket.onmessage = null;
    _lspSocket.onopen = null;
    _lspSocket.close();
    _lspSocket = null;
  }
  _lspConnected = false;
  _rejectAllPending('LSP disconnected');
  if (!keepDocuments) {
    _lspOpenDocuments = {};
  }
  _lspPendingRequests = {};
  _lspRequestId = 1;
  unregisterLspProviders();
}

function isLspConnected() {
  return _lspConnected;
}

// --- Request / notification transport ---

function sendLspRequest(method, params, profileId) {
  return new Promise(function(resolve, reject) {
    if (!_lspConnected || !_lspSocket) {
      reject(new Error('LSP not connected'));
      return;
    }
    if (!profileId) {
      reject(new Error('No LSP profile for this language'));
      return;
    }

    var id = _lspRequestId++;
    var timer = setTimeout(function() {
      var pending = _lspPendingRequests[id];
      if (pending) {
        delete _lspPendingRequests[id];
        pending.reject(new Error('LSP request timeout'));
      }
    }, 10000);

    _lspPendingRequests[id] = { resolve: resolve, reject: reject, timer: timer };

    _lspSocket.send(JSON.stringify({ id: id, method: method, params: params, profile_id: profileId }));
  });
}

function sendLspNotification(method, params, profileId) {
  if (!_lspConnected || !_lspSocket || !profileId) return;
  _lspSocket.send(JSON.stringify({ method: method, params: params, profile_id: profileId }));
}

// --- Document lifecycle ---

function lspDidOpenDocument(filePath, content, languageId) {
  var uri = pathToLspUri(filePath);
  var version = 1;
  var profileId = getProfileIdForLanguage(languageId);
  _lspOpenDocuments[uri] = { languageId: languageId, version: version, text: content, profileId: profileId };

  if (_lspConnected && profileId) {
    sendLspNotification('textDocument/didOpen', {
      textDocument: {
        uri: uri,
        languageId: languageId,
        version: version,
        text: content
      }
    }, profileId);
  }
}

function lspDidCloseDocument(filePath) {
  var uri = pathToLspUri(filePath);
  var doc = _lspOpenDocuments[uri];
  if (!doc) return;

  var profileId = doc.profileId;
  delete _lspOpenDocuments[uri];

  sendLspNotification('textDocument/didClose', {
    textDocument: { uri: uri }
  }, profileId);
}

// --- LSP feature requests ---

function _getProfileForFile(filePath) {
  var uri = pathToLspUri(filePath);
  var doc = _lspOpenDocuments[uri];
  if (!doc) return null;
  if (doc.profileId) return doc.profileId;
  var resolved = getProfileIdForLanguage(doc.languageId);
  if (resolved) doc.profileId = resolved;
  return resolved;
}

function lspGoToDefinition(filePath, line, column) {
  if (!_lspConnected) return Promise.resolve(null);
  var profileId = _getProfileForFile(filePath);
  if (!profileId) return Promise.resolve(null);

  return sendLspRequest('textDocument/definition', {
    textDocument: { uri: pathToLspUri(filePath) },
    position: { line: line - 1, character: column - 1 }
  }, profileId);
}

function lspHover(filePath, line, column) {
  if (!_lspConnected) return Promise.resolve(null);
  var profileId = _getProfileForFile(filePath);
  if (!profileId) return Promise.resolve(null);

  return sendLspRequest('textDocument/hover', {
    textDocument: { uri: pathToLspUri(filePath) },
    position: { line: line - 1, character: column - 1 }
  }, profileId);
}

function lspReferences(filePath, line, column) {
  if (!_lspConnected) return Promise.resolve(null);
  var profileId = _getProfileForFile(filePath);
  if (!profileId) return Promise.resolve(null);

  return sendLspRequest('textDocument/references', {
    textDocument: { uri: pathToLspUri(filePath) },
    position: { line: line - 1, character: column - 1 },
    context: { includeDeclaration: true }
  }, profileId);
}

// --- Monaco provider registration ---

function registerLspProviders(editor, filePath, languageId) {
  unregisterLspProviders();

  window._monacoReady.then(function() {
    var defDisposable = monaco.languages.registerDefinitionProvider(languageId, {
      provideDefinition: function(model, position) {
        return lspGoToDefinition(filePath, position.lineNumber, position.column)
          .then(function(result) {
            if (!result) return null;
            var locations = Array.isArray(result) ? result : [result];
            if (locations.length === 0) return null;

            return locations.map(function(loc) {
              var targetPath = lspUriToPath(loc.uri);
              var range = new monaco.Range(
                loc.range.start.line + 1,
                loc.range.start.character + 1,
                loc.range.end.line + 1,
                loc.range.end.character + 1
              );

              if (targetPath === filePath) {
                return { uri: model.uri, range: range };
              }
              return { uri: monaco.Uri.parse(loc.uri), range: range };
            });
          })
          .catch(function() { return null; });
      }
    });

    var hoverDisposable = monaco.languages.registerHoverProvider(languageId, {
      provideHover: function(model, position) {
        return lspHover(filePath, position.lineNumber, position.column)
          .then(function(result) {
            if (!result || !result.contents) return null;

            var contents = _convertHoverContents(result.contents);
            if (contents.length === 0) return null;

            var hover = { contents: contents };
            if (result.range) {
              hover.range = _lspRangeToMonaco(result.range);
            }
            return hover;
          })
          .catch(function() { return null; });
      }
    });

    var refDisposable = monaco.languages.registerReferenceProvider(languageId, {
      provideReferences: function(model, position, context) {
        return lspReferences(filePath, position.lineNumber, position.column)
          .then(function(result) {
            if (!result) return null;
            var locations = Array.isArray(result) ? result : [result];
            return locations.map(lspLocationToMonaco);
          })
          .catch(function() { return null; });
      }
    });

    _lspProviderDisposables.push(defDisposable, hoverDisposable, refDisposable);
  });
}

function unregisterLspProviders() {
  _lspProviderDisposables.forEach(function(d) {
    if (d && typeof d.dispose === 'function') {
      d.dispose();
    }
  });
  _lspProviderDisposables = [];
}

// --- URI / location helpers ---

function pathToLspUri(relativePath) {
  var base = (typeof _lspProjectPath !== 'undefined' && _lspProjectPath) ? _lspProjectPath : '';
  if (base && relativePath.indexOf('/') !== 0) {
    // Path is relative — prepend project root
    var absPath = base.replace(/\/$/, '') + '/' + relativePath;
    return 'file://' + absPath;
  }
  return 'file://' + relativePath;
}

function lspUriToPath(uri) {
  var absPath = uri;
  if (absPath.indexOf('file://') === 0) {
    absPath = absPath.substring(7);
  }
  // Convert back to relative path if under project root
  var base = (typeof _lspProjectPath !== 'undefined' && _lspProjectPath) ? _lspProjectPath : '';
  if (base && absPath.indexOf(base) === 0) {
    var rel = absPath.substring(base.length);
    if (rel.charAt(0) === '/') rel = rel.substring(1);
    return rel;
  }
  return absPath;
}

function lspLocationToMonaco(loc) {
  return {
    uri: monaco.Uri.parse(loc.uri),
    range: _lspRangeToMonaco(loc.range)
  };
}

function _lspRangeToMonaco(range) {
  return new monaco.Range(
    range.start.line + 1,
    range.start.character + 1,
    range.end.line + 1,
    range.end.character + 1
  );
}

// --- Internal helpers ---

function _handleLspMessage(msg) {
  if (msg.id != null && _lspPendingRequests[msg.id]) {
    var pending = _lspPendingRequests[msg.id];
    delete _lspPendingRequests[msg.id];
    clearTimeout(pending.timer);

    if (msg.error) {
      pending.reject(new Error(msg.error.message || 'LSP error'));
    } else {
      pending.resolve(msg.result);
    }
  }
}

function _rejectAllPending(reason) {
  var ids = Object.keys(_lspPendingRequests);
  ids.forEach(function(id) {
    var pending = _lspPendingRequests[id];
    clearTimeout(pending.timer);
    pending.reject(new Error(reason));
  });
  _lspPendingRequests = {};
}

function _scheduleReconnect() {
  if (_lspReconnectTimer) return;
  _lspReconnectTimer = setTimeout(function() {
    _lspReconnectTimer = null;
    connectLsp();
  }, 3000);
}

function _resendOpenDocuments() {
  updateLspLanguageMap();
  var uris = Object.keys(_lspOpenDocuments);
  uris.forEach(function(uri) {
    var doc = _lspOpenDocuments[uri];
    doc.profileId = getProfileIdForLanguage(doc.languageId);
    sendLspNotification('textDocument/didOpen', {
      textDocument: {
        uri: uri,
        languageId: doc.languageId,
        version: doc.version,
        text: doc.text || ''
      }
    }, doc.profileId);
  });
}

function _convertHoverContents(contents) {
  if (typeof contents === 'string') {
    return [{ value: contents }];
  }
  if (contents && typeof contents === 'object' && !Array.isArray(contents)) {
    if (contents.kind) {
      return [{ value: contents.value }];
    }
    if (contents.language) {
      return [{ value: '```' + contents.language + '\n' + contents.value + '\n```' }];
    }
    return [{ value: String(contents.value || '') }];
  }
  if (Array.isArray(contents)) {
    return contents.map(function(item) {
      if (typeof item === 'string') {
        return { value: item };
      }
      if (item.language) {
        return { value: '```' + item.language + '\n' + item.value + '\n```' };
      }
      return { value: item.value || '' };
    });
  }
  return [];
}
