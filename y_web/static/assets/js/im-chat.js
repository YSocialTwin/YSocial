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
  /* Infinite scrolling (setting "infinite_scroll_enabled"): load the older page when the link scrolls into view. */
  var box = document.getElementById('im-messages');
  var more = document.querySelector('[data-im-more="older"]');
  if (body.getAttribute('data-infinite') === '1' && box && more && 'IntersectionObserver' in window) {
    var busy = false;
    var io = new IntersectionObserver(function (entries) {
      if (busy || !entries[0].isIntersecting) return;
      var link = document.querySelector('[data-im-more="older"]');
      if (!link) return;
      busy = true;
      fetch(link.href, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (!html) { busy = false; return; }
          var doc = new DOMParser().parseFromString(html, 'text/html');
          var older = doc.getElementById('im-messages');
          var next = doc.querySelector('[data-im-more="older"]');
          if (older) {
            var first = box.firstChild;
            Array.prototype.slice.call(older.children).forEach(function (n) { box.insertBefore(document.importNode(n, true), first); });
          }
          if (next) { link.href = next.href; link.setAttribute('data-before', next.getAttribute('data-before')); busy = false; }
          else { link.parentNode.remove(); io.disconnect(); }
        })
        .catch(function () { busy = false; });
    });
    io.observe(more);
  }
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
