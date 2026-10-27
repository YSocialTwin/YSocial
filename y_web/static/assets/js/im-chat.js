/* Instant messaging observer: theme toggle and polling while the simulation runs. No dependency. */
(function () {
  'use strict';
  var root = document.documentElement;
  function safe(fn) { try { return fn(); } catch (e) { return null; } }
  var saved = safe(function () { return localStorage.getItem('im-theme'); });
  if (saved === 'dark' || saved === 'light') root.setAttribute('data-theme', saved);
  var toggle = document.getElementById('im-theme');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var dark = root.getAttribute('data-theme') === 'dark';
      var next = dark ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      safe(function () { localStorage.setItem('im-theme', next); });
    });
  }
  var body = document.body;
  var seconds = parseInt(body.getAttribute('data-poll') || '0', 10);
  var latest = parseInt(body.getAttribute('data-latest') || '0', 10);
  var url = body.getAttribute('data-status-url');
  var banner = document.getElementById('im-live');
  if (!seconds || !url || !banner) return;
  var timer = setInterval(function () {
    if (document.hidden) return;
    fetch(url + '?after=' + latest, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s) return;
        if (s.changed) banner.hidden = false;
        if (!s.running) clearInterval(timer);
      })
      .catch(function () {});
  }, seconds * 1000);
})();
