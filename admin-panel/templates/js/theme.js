// ═══════════════════════════════════════════════
//  THEME
// ═══════════════════════════════════════════════
function _updateThemeButtons(theme) {
  var icon = theme === 'dark' ? '☀' : '☾';
  var headerBtn = document.getElementById('themeBtn');
  if (headerBtn) headerBtn.textContent = icon;
  var selectorBtn = document.getElementById('selectorThemeBtn');
  if (selectorBtn) selectorBtn.textContent = icon;
}

function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('admin-panel-theme', state.theme);
  document.documentElement.setAttribute('data-theme', state.theme);
  _updateThemeButtons(state.theme);
  var hljsLink = document.getElementById('hljs-theme');
  if (hljsLink) {
    hljsLink.href = state.theme === 'dark'
      ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
      : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  }
  if (typeof updateTerminalTheme === 'function') updateTerminalTheme();
  if (typeof updateEditorTheme === 'function') updateEditorTheme(state.theme);
  if (state.selectedFile) renderDiff(state.selectedFile);
  // Re-initialize mermaid with new theme and re-render diagrams
  if (typeof mermaid !== 'undefined' && typeof getMermaidTheme === 'function') {
    mermaid.initialize(Object.assign({ startOnLoad: false }, getMermaidTheme()));
    if (typeof renderSystemDiagram === 'function') renderSystemDiagram();
    if (typeof renderMermaidDiagram === 'function') renderMermaidDiagram();
  }
}

(function initTheme() {
  var saved = localStorage.getItem('admin-panel-theme');
  if (saved && (saved === 'dark' || saved === 'light')) {
    state.theme = saved;
    document.documentElement.setAttribute('data-theme', saved);
    _updateThemeButtons(saved);
    var hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
      hljsLink.href = saved === 'dark'
        ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
        : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
    }
  }
})();
