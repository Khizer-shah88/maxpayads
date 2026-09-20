/**
 * Removes the source-view deterrent service worker.
 *
 * Turning the ENABLE_SOURCE_DETERRENT flag off stops new registrations but does
 * NOT remove a worker already installed in a visitor's browser. That worker
 * keeps controlling the origin until something unregisters it. Ship this for
 * one release when standing the feature down.
 *
 * You normally do not need this: /source-deterrent-sw.js is itself a tombstone
 * that unregisters on activate, so any client that can fetch an update clears
 * itself. This script is the belt-and-braces path for a client whose update
 * check has not fired yet.
 *
 * Console equivalent, if you only need to clear your own browser:
 *   navigator.serviceWorker.getRegistrations()
 *     .then(rs => rs.forEach(r => r.unregister()))
 *
 * Scoped ON PURPOSE. The previous version unregistered every registration on
 * the origin, including any unrelated worker, in its else-branch. This one
 * touches only workers whose script URL is ours.
 */
(function () {
  if (!('serviceWorker' in navigator)) return;

  var OURS = /\/(source-deterrent-sw|unregister-source-deterrent)\.js(\?|$)/;

  function isOurs(registration) {
    var w = registration.active || registration.waiting || registration.installing;
    return !!(w && w.scriptURL && OURS.test(w.scriptURL));
  }

  navigator.serviceWorker.getRegistrations().then(function (registrations) {
    registrations.filter(isOurs).forEach(function (registration) {
      registration.unregister().then(function (ok) {
        if (ok) console.log('[source-deterrent] unregistered', registration.scope);
      });
    });
  }).catch(function () {
    // Nothing to do -- no registrations readable in this context.
  });
})();
