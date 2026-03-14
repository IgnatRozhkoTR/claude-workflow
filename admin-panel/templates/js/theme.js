// ═══════════════════════════════════════════════
//  THEME
// ═══════════════════════════════════════════════
function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('admin-panel-theme', state.theme);
  document.documentElement.setAttribute('data-theme', state.theme);
  document.getElementById('themeBtn').textContent = state.theme === 'dark' ? '☀' : '☾';
  var hljsLink = document.getElementById('hljs-theme');
  if (hljsLink) {
    hljsLink.href = state.theme === 'dark'
      ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
      : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  }
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
    document.getElementById('themeBtn').textContent = saved === 'dark' ? '☀' : '☾';
    var hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
      hljsLink.href = saved === 'dark'
        ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
        : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
    }
  }
})();
