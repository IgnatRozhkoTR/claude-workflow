// ═══════════════════════════════════════════════
//  INTERNATIONALIZATION (i18n)
// ═══════════════════════════════════════════════

if (typeof I18N_LOCALE === 'undefined') var I18N_LOCALE = 'en';
if (typeof I18N_MESSAGES === 'undefined') var I18N_MESSAGES = {};

function t(key, params) {
  var msg = I18N_MESSAGES[key];
  if (msg === undefined || msg === null) return key;
  if (!params) return msg;
  return msg.replace(/\{(\w+)\}/g, function(match, name) {
    return params[name] !== undefined ? params[name] : match;
  });
}

function applyI18nToDOM() {
  document.querySelectorAll('[data-i18n]').forEach(function(el) {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
    el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
  });
  document.querySelectorAll('[data-i18n-title]').forEach(function(el) {
    el.title = t(el.getAttribute('data-i18n-title'));
  });
}

function loadI18n(locale) {
  return fetch('/i18n/' + locale + '.json')
    .then(function(resp) {
      if (!resp.ok) throw new Error('Failed to load locale: ' + locale);
      return resp.json();
    })
    .then(function(messages) {
      I18N_MESSAGES = messages;
      I18N_LOCALE = locale;
      applyI18nToDOM();
    })
    .catch(function(e) {
      console.warn('i18n load failed for locale "' + locale + '":', e.message);
    });
}

function setLocale(locale) {
  var ctx = typeof getWorkspaceContext === 'function' ? getWorkspaceContext() : null;
  var url = ctx
    ? '/api/ws/' + encodeURIComponent(ctx.projectId) + '/' + encodeURIComponent(ctx.branch) + '/locale'
    : null;

  var persist = url
    ? fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locale: locale })
      }).catch(function(e) { console.warn('Failed to persist locale:', e.message); })
    : Promise.resolve();

  persist.then(function() {
    return loadI18n(locale);
  }).then(function() {
    var activeTab = null;
    document.querySelectorAll('.tab-btn.active').forEach(function(btn) {
      activeTab = btn.dataset.tab;
    });
    if (activeTab && typeof switchTab === 'function') {
      switchTab(activeTab);
    }
    if (typeof renderPhaseBar === 'function') {
      renderPhaseBar('phaseBarControl', 'phaseLabelsControl');
    }
    // Update header phase label
    var phaseLabel = document.getElementById('phaseLabel');
    if (phaseLabel && typeof LOCK_DATA !== 'undefined' && LOCK_DATA.phase) {
      var name = typeof getPhaseName === 'function' ? getPhaseName(LOCK_DATA.phase) : LOCK_DATA.phase;
      phaseLabel.textContent = t('phase.label', {phase: LOCK_DATA.phase, name: name});
    }
  });
}
