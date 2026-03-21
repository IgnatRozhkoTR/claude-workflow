// ═══════════════════════════════════════════════
//  EVENT BUS (pub/sub)
// ═══════════════════════════════════════════════
var EventBus = (function() {
  var listeners = {};

  function on(event, callback) {
    if (!listeners[event]) listeners[event] = [];
    listeners[event].push(callback);
  }

  function off(event, callback) {
    if (!listeners[event]) return;
    listeners[event] = listeners[event].filter(function(cb) { return cb !== callback; });
  }

  function emit(event, data) {
    if (!listeners[event]) return;
    listeners[event].forEach(function(cb) { cb(data); });
  }

  return { on: on, off: off, emit: emit };
})();
