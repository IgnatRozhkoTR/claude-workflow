// ═══════════════════════════════════════════════
//  MONACO EDITOR
// ═══════════════════════════════════════════════

var _monacoExtensionMap = {
  py: 'python',
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  ts: 'typescript',
  jsx: 'javascript',
  tsx: 'typescript',
  java: 'java',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  cpp: 'cpp',
  cc: 'cpp',
  cxx: 'cpp',
  hpp: 'cpp',
  c: 'c',
  h: 'c',
  html: 'html',
  htm: 'html',
  css: 'css',
  scss: 'scss',
  less: 'less',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  md: 'markdown',
  markdown: 'markdown',
  xml: 'xml',
  svg: 'xml',
  sql: 'sql',
  sh: 'shell',
  bash: 'shell',
  zsh: 'shell',
  kt: 'kotlin',
  kts: 'kotlin',
  swift: 'swift',
  dart: 'dart',
  php: 'php',
  cs: 'csharp',
  r: 'r',
  lua: 'lua',
  perl: 'perl',
  pl: 'perl',
  vue: 'html',
  svelte: 'html',
  graphql: 'graphql',
  gql: 'graphql',
  toml: 'ini',
  ini: 'ini',
  cfg: 'ini',
  dockerfile: 'dockerfile',
  makefile: 'makefile'
};

function getMonacoLanguage(filePath) {
  var name = filePath.split('/').pop().toLowerCase();
  if (name === 'dockerfile') return 'dockerfile';
  if (name === 'makefile' || name === 'gnumakefile') return 'makefile';

  var ext = name.split('.').pop();
  if (ext === name) return 'plaintext';
  return _monacoExtensionMap[ext] || 'plaintext';
}

function initMonaco() {
  require.config({
    paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs' }
  });

  window._monacoReady = new Promise(function(resolve) {
    require(['vs/editor/editor.main'], function() {
      monaco.editor.registerEditorOpener({
        openCodeEditor: function(source, resource, selectionOrPosition) {
          var path = resource.path;
          var relativePath = (typeof lspUriToPath === 'function')
            ? lspUriToPath(resource.toString())
            : path;

          var lineNumber = null;
          if (selectionOrPosition) {
            if (typeof selectionOrPosition.startLineNumber === 'number') {
              lineNumber = selectionOrPosition.startLineNumber;
            } else if (typeof selectionOrPosition.lineNumber === 'number') {
              lineNumber = selectionOrPosition.lineNumber;
            }
          }

          if (typeof selectExplorerFile === 'function') {
            selectExplorerFile(relativePath, lineNumber);
            return true;
          }
          return false;
        }
      });

      resolve();
    });
  });
}

function createEditor(container, content, language, filePath) {
  return window._monacoReady.then(function() {
    if (window._monacoEditor) {
      window._monacoEditor.dispose();
      window._monacoEditor = null;
    }

    var editor = monaco.editor.create(container, {
      value: content,
      language: language,
      readOnly: true,
      theme: state.theme === 'dark' ? 'vs-dark' : 'vs',
      automaticLayout: true,
      minimap: { enabled: true },
      scrollBeyondLastLine: false,
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      lineNumbers: 'on',
      renderWhitespace: 'selection',
      wordWrap: 'on'
    });

    window._monacoEditor = editor;
    window._monacoCurrentFile = filePath;

    if (typeof applyLspShortcuts === 'function') {
      applyLspShortcuts();
    }

    return editor;
  });
}

function disposeEditor() {
  if (window._monacoEditor) {
    window._monacoEditor.dispose();
    window._monacoEditor = null;
  }
}

function updateEditorTheme(theme) {
  if (typeof monaco !== 'undefined') {
    monaco.editor.setTheme(theme === 'dark' ? 'vs-dark' : 'vs');
  }
}

function revealLine(lineNumber) {
  if (window._monacoEditor) {
    window._monacoEditor.revealLineInCenter(lineNumber);
    window._monacoEditor.setPosition({ lineNumber: lineNumber, column: 1 });
  }
}
