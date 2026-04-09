// ═══════════════════════════════════════════════
//  API CLIENT
// ═══════════════════════════════════════════════

const API_BASE = '';  // Same origin

// ─── URL-based workspace context ───

function getWorkspaceContext() {
  const params = new URLSearchParams(window.location.search);
  const ws = params.get('ws');
  if (!ws) return null;

  const slashIdx = ws.indexOf('/');
  if (slashIdx === -1) return null;

  return {
    projectId: ws.substring(0, slashIdx),
    branch: ws.substring(slashIdx + 1)
  };
}

function setWorkspaceContext(projectId, branch) {
  const url = new URL(window.location);
  url.searchParams.set('ws', projectId + '/' + branch);
  window.history.pushState({}, '', url);
}

function clearWorkspaceContext() {
  const url = new URL(window.location);
  url.searchParams.delete('ws');
  window.history.pushState({}, '', url);
}

// ─── Generic fetch helpers ───

async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.details || res.statusText);
  }
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.details || res.statusText);
  }
  return res.json();
}

async function apiPut(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.details || res.statusText);
  }
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(API_BASE + path, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.details || res.statusText);
  }
  return res.json();
}

// ─── Project endpoints ───

function apiListProjects() {
  return apiGet('/api/projects');
}

function apiRegisterProject(name, path) {
  return apiPost('/api/projects', { name, path });
}

function apiDeleteProject(id) {
  return apiDelete('/api/projects/' + encodeURIComponent(id));
}

// ─── Branch & workspace endpoints ───

function apiListBranches(projectId) {
  return apiGet('/api/projects/' + encodeURIComponent(projectId) + '/branches');
}

function apiListWorkspaces(projectId) {
  return apiGet('/api/projects/' + encodeURIComponent(projectId) + '/workspaces');
}

function apiCreateWorkspace(projectId, branch, source, worktree) {
  return apiPost('/api/projects/' + encodeURIComponent(projectId) + '/workspaces', {
    branch, source, worktree
  });
}

function apiArchiveWorkspace(projectId, branch) {
  return apiPut('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/archive');
}

// ─── Workspace state endpoints ───

function apiGetState(projectId, branch) {
  return apiGet('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/state');
}

function apiSetScope(projectId, branch, scope) {
  return apiPut('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/scope', { scope });
}

function apiSetPhase(projectId, branch, phase) {
  return apiPut('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/phase', { phase: phase });
}

function apiAddComment(projectId, branch, scope, target, text, filePath, lineStart, lineEnd, lHash) {
  var body = { scope: scope, target: target, text: text };
  if (filePath) body.file_path = filePath;
  if (lineStart != null) body.line_start = lineStart;
  if (lineEnd != null) body.line_end = lineEnd;
  if (lHash) body.line_hash = lHash;
  return apiPost('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/comments', body);
}

function apiResolveComment(projectId, branch, commentId, resolved) {
  return apiPut('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/comments/' + commentId + '/resolve', { resolved: resolved });
}

function apiListComments(projectId, branch, scope, showResolved) {
  var url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/comments';
  var params = [];
  if (scope) params.push('scope=' + encodeURIComponent(scope));
  if (showResolved) params.push('resolved=true');
  if (params.length) url += '?' + params.join('&');
  return apiGet(url);
}

function apiSavePlan(projectId, branch, planData) {
  return apiPut('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/plan', planData);
}

function apiAdvance(projectId, branch, body) {
  return apiPost('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/advance', body || {});
}

function apiGetGateNonce(projectId, branch) {
  return apiGet('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/gate-nonce');
}

function apiApprove(projectId, branch, token, commitMessage) {
  var body = { token: token };
  if (commitMessage) body.commit_message = commitMessage;
  return apiPost('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/approve', body);
}

function apiReject(projectId, branch, token, comments) {
  return apiPost('/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/reject', { token: token, comments: comments });
}

// ─── File & diff endpoints ───

function apiReadFile(projectId, branch, filePath, startLine, endLine, absolute) {
  let url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/file?path=' + encodeURIComponent(filePath);
  if (startLine != null) url += '&start=' + startLine;
  if (endLine != null) url += '&end=' + endLine;
  if (absolute) url += '&absolute=true';
  return apiGet(url);
}

function apiGetDiff(projectId, branch, mode, commit) {
  var url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/diff';
  var q = [];
  if (mode && mode !== 'branch') q.push('mode=' + encodeURIComponent(mode));
  if (commit) q.push('commit=' + encodeURIComponent(commit));
  if (q.length) url += '?' + q.join('&');
  return apiGet(url);
}

function apiGetCommitHistory(projectId, branch) {
  var url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/history';
  return apiGet(url);
}

function apiHistoryRename(projectId, branch, message) {
  var url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/history/rename';
  return apiPost(url, { message: message });
}

function apiHistoryUndo(projectId, branch) {
  var url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/history/undo';
  return apiPost(url, {});
}

function apiHistorySquash(projectId, branch, commits, message) {
  var url = '/api/ws/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(branch) + '/history/squash';
  return apiPost(url, { commits: commits, message: message });
}
