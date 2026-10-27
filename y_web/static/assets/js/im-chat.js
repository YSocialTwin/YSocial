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
  /* Info panel (Telegram-style right pane): remembered per browser. */
  var info = document.getElementById('im-info'), itog = document.getElementById('im-info-toggle'), iclose = document.getElementById('im-info-close');
  var app = document.querySelector('.im-app');
  function showInfo(on) {
    if (!info) return;
    info.hidden = !on;
    if (app) app.classList.toggle('has-info', on);
    if (itog) itog.setAttribute('aria-expanded', on ? 'true' : 'false');
    safe(function () { localStorage.setItem('im-info', on ? '1' : '0'); });
  }
  if (info) {
    if (app) app.classList.remove('has-info');
    if (safe(function () { return localStorage.getItem('im-info'); }) === '1' && window.innerWidth > 1100) showInfo(true);
    if (itog) itog.addEventListener('click', function () { showInfo(info.hidden); });
    if (iclose) iclose.addEventListener('click', function () { showInfo(false); });
  }
  /* The menu closes on outside click and Escape. */
  var menu = document.getElementById('im-menu');
  if (menu) {
    document.addEventListener('click', function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.open) { menu.open = false; var s = menu.querySelector('summary'); if (s) s.focus(); } });
  }
  /* Structured search (Telegram-Web-like): focusing the box opens an overlay over the chat list with one tab per
     kind of result; results follow what is typed. Without JavaScript the form still opens the plain results page. */
  var form = document.getElementById('im-search'), find = document.getElementById('im-find');
  if (form && find && window.fetch) {
    var input = document.getElementById('im-q'), side = form.closest('.im-side');
    var list = document.getElementById('im-find-list'), msg = document.getElementById('im-find-msg');
    var tabs = Array.prototype.slice.call(find.querySelectorAll('[role="tab"]'));
    var kind = safe(function () { return sessionStorage.getItem('im-find-kind'); }) || 'chats';
    var timer = null, seq = 0, closer = null;
    var base = form.getAttribute('data-find-url'), extra = form.getAttribute('data-find-params') || '';
    function paint() {
      tabs.forEach(function (t) {
        var on = t.getAttribute('data-kind') === kind;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
      });
    }
    function open() {
      if (!find.hidden) return;
      find.hidden = false;
      if (side) side.classList.add('is-finding');
      paint();
      if (!closer) {
        closer = document.createElement('button');
        closer.type = 'button'; closer.className = 'im-icon-btn im-find-back';
        closer.setAttribute('aria-label', find.getAttribute('aria-label') + ' ×');
        closer.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        closer.addEventListener('click', close);
        form.parentNode.insertBefore(closer, form);
      }
    }
    function close() {
      find.hidden = true;
      if (side) side.classList.remove('is-finding');
      if (closer) { closer.remove(); closer = null; }
      input.value = '';
      list.textContent = '';
      seq++;
    }
    function row(r) {
      var li = document.createElement('li'), a = document.createElement('a');
      a.href = r.href; a.className = 'im-find-row';
      var av = document.createElement('span');
      av.className = 'im-avatar is-md'; av.style.setProperty('--im-hue', r.hue);
      av.textContent = (r.title || '?').trim().charAt(0).toUpperCase();
      var main = document.createElement('span'); main.className = 'im-find-main';
      var t = document.createElement('span'); t.className = 'im-find-title'; t.textContent = r.title;
      main.appendChild(t);
      if (r.subtitle) { var sub = document.createElement('span'); sub.className = 'im-find-sub'; sub.textContent = r.subtitle; main.appendChild(sub); }
      if (r.snippet) { var sn = document.createElement('span'); sn.className = 'im-find-snippet'; sn.textContent = r.snippet; main.appendChild(sn); }
      a.appendChild(av); a.appendChild(main); li.appendChild(a);
      return li;
    }
    function run() {
      var q = input.value.trim(), mine = ++seq;
      var url = base + '?' + (extra ? extra + '&' : '') + 'kind=' + encodeURIComponent(kind) + '&q=' + encodeURIComponent(q);
      fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d || mine !== seq) return;
          list.textContent = '';
          d.results.forEach(function (r) { list.appendChild(row(r)); });
          msg.textContent = d.message || '';
          msg.hidden = !d.message;
        })
        .catch(function () {});
    }
    function schedule() { clearTimeout(timer); timer = setTimeout(run, 180); }
    input.addEventListener('focus', function () { open(); if (input.value.trim()) run(); });
    input.addEventListener('input', function () { open(); schedule(); });
    form.addEventListener('submit', function (e) { e.preventDefault(); clearTimeout(timer); run(); });
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        kind = t.getAttribute('data-kind');
        safe(function () { sessionStorage.setItem('im-find-kind', kind); });
        paint(); run(); input.focus();
      });
      t.addEventListener('keydown', function (e) {
        var i = tabs.indexOf(t), n = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : -1;
        if (n < 0) return;
        e.preventDefault();
        tabs[(n + tabs.length) % tabs.length].click();
      });
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !find.hidden) { close(); input.blur(); } });
    paint();
    if (input.value.trim()) { open(); run(); }
  }
  /* Open a conversation at its latest message (or at the linked one). */
  var scroller = document.getElementById('im-scroll');
  if (scroller) {
    var target = location.hash && document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView({ block: 'center' }); else scroller.scrollTop = scroller.scrollHeight;
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
