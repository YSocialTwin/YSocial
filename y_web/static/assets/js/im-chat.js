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
    var canJoin = document.body.getAttribute('data-participant') === '1' && document.body.getAttribute('data-writable') === '1';
    function row(r) {
      var li = document.createElement('li'), a = document.createElement('a');
      li.className = 'im-find-item';
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
      if (canJoin && r.chat_id && r.type !== 'private' && !r.joined) {
        /* the participant script handles [data-im-do]; "data-go" opens the chat afterwards */
        var j = document.createElement('button');
        j.type = 'button'; j.className = 'im-act im-find-join';
        j.setAttribute('data-im-do', 'join'); j.setAttribute('data-chat', r.chat_id); j.setAttribute('data-go', '1');
        j.textContent = form.getAttribute('data-t-join') || 'Join';
        li.appendChild(j);
      }
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
    scroller.style.scrollBehavior = 'auto';
    if (target) target.scrollIntoView({ block: 'center' }); else scroller.scrollTop = scroller.scrollHeight;
    scroller.style.scrollBehavior = '';
  }
  var body = document.body;
  var box = document.getElementById('im-messages');
  var seconds = parseInt(body.getAttribute('data-poll') || '0', 10);
  var latest = parseInt(body.getAttribute('data-latest') || '0', 10);
  var url = body.getAttribute('data-status-url');
  var banner = document.getElementById('im-live');

  /* Conversation: messages are in chronological order, the oldest are loaded while scrolling up and, while the
     simulation runs, the new ones are appended at the bottom (the page is only fetched, never reloaded). */
  function parsePage(href) {
    return fetch(href, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { return html ? new DOMParser().parseFromString(html, 'text/html') : null; });
  }
  function chipText(n) { return n && n.classList && n.classList.contains('im-day-chip') ? n.textContent.trim() : null; }
  function messageNodes(doc) { var b = doc.getElementById('im-messages'); return b ? Array.prototype.slice.call(b.children) : []; }
  var live = !!(scroller && box);
  if (live) {
    var infinite = body.getAttribute('data-infinite') === '1';
    var busyOld = false, busyNew = false, unseen = 0, pill = null;
    function nearBottom() { return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 140; }
    function keepPosition(fn) {
      var prevStyle = scroller.style.scrollBehavior, h = scroller.scrollHeight, t = scroller.scrollTop;
      scroller.style.scrollBehavior = 'auto';
      fn();
      scroller.scrollTop = t + (scroller.scrollHeight - h);
      scroller.style.scrollBehavior = prevStyle;
    }
    function loadOlder() {
      var link = document.querySelector('[data-im-more="older"]');
      if (!infinite || busyOld || !link) return;
      busyOld = true;
      parsePage(link.href).then(function (doc) {
        if (!doc) { busyOld = false; return; }
        var nodes = messageNodes(doc), next = doc.querySelector('[data-im-more="older"]');
        keepPosition(function () {
          var first = box.firstElementChild;
          var chips = nodes.filter(function (n) { return chipText(n) !== null; });
          if (chips.length && chipText(first) !== null && chipText(first) === chipText(chips[chips.length - 1])) box.removeChild(first);
          var anchor = box.firstChild;
          nodes.forEach(function (n) { if (!n.id || !document.getElementById(n.id)) box.insertBefore(document.importNode(n, true), anchor); });
        });
        if (next) { link.href = next.href; link.setAttribute('data-before', next.getAttribute('data-before')); }
        else { link.parentNode.remove(); }
        busyOld = false;
        if (next) fill();
      }).catch(function () { busyOld = false; });
    }
    /* keep loading while the top of the conversation is near or the page does not fill the pane */
    function fill(initial) { if ((!initial && scroller.scrollTop < 240) || scroller.scrollHeight <= scroller.clientHeight + 240) loadOlder(); }
    scroller.addEventListener('scroll', function () { if (scroller.scrollTop < 240) loadOlder(); if (pill && nearBottom()) dropPill(); }, { passive: true });
    setTimeout(function () { fill(true); }, 150);

    function dropPill() { if (pill) { pill.remove(); pill = null; unseen = 0; } }
    function showPill(n) {
      unseen += n;
      if (!pill) {
        pill = document.createElement('button');
        pill.type = 'button'; pill.className = 'im-newpill';
        pill.addEventListener('click', function () { scroller.scrollTop = scroller.scrollHeight; dropPill(); });
        scroller.parentNode.appendChild(pill);
      }
      pill.textContent = '↓ ' + unseen;
    }
    function lastId() {
      var all = box.querySelectorAll('article.im-msg');
      return all.length ? all[all.length - 1].id.replace(/^m-/, '') : null;
    }
    function loadNewer() {
      if (busyNew || document.querySelector('[data-im-more="newer"]')) return Promise.resolve();
      var id = lastId();
      busyNew = true;
      var u = new URL(location.href);
      u.hash = ''; u.searchParams.delete('before');
      if (id) u.searchParams.set('after', id); else u.searchParams.delete('after');
      return parsePage(u.href).then(function (doc) {
        busyNew = false;
        if (!doc) return;
        var stick = nearBottom(), added = 0, nodes = messageNodes(doc);
        nodes.forEach(function (n) {
          if (n.tagName === 'P' && n.classList.contains('im-empty')) return;
          if (n.id && document.getElementById(n.id)) return;
          var chip = chipText(n);
          if (chip !== null) {
            var lastChip = Array.prototype.filter.call(box.children, function (c) { return chipText(c) !== null; }).pop();
            if (lastChip && chipText(lastChip) === chip) return;
          }
          var empty = box.querySelector('.im-empty'); if (empty) empty.remove();
          box.appendChild(document.importNode(n, true));
          if (n.classList.contains('im-msg')) added++;
        });
        if (added) { if (stick) scroller.scrollTop = scroller.scrollHeight; else showPill(added); }
        if (doc.querySelector('[data-im-more="newer"]')) return loadNewer();
      }).catch(function () { busyNew = false; });
    }
    window.imLoadNewer = loadNewer;
  }

  if (!seconds || !url) return;
  var timer = setInterval(function () {
    if (document.hidden) return;
    fetch(url + '?after=' + latest, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s) return;
        if (s.changed) {
          latest = s.round || latest;
          if (live && window.imLoadNewer) window.imLoadNewer();
          else if (banner) banner.hidden = false;
        }
        if (!s.running) clearInterval(timer);
      })
      .catch(function () {});
  }, seconds * 1000);
})();

/* Link cards: the image (and a title, when the news snapshot has none) is read from the article page after the
   chat is shown, so a slow or unreachable site never delays the messages. */
(function () {
  var exp = document.body.getAttribute('data-exp');
  if (!exp || !window.fetch) return;
  var queue = [], running = 0;
  function fill(card, data) {
    card.removeAttribute('data-preview-pending');
    if (!data) return;
    var body = card.querySelector('.im-link-body');
    if (data.image && !card.querySelector('.im-link-img')) {
      var img = document.createElement('img');
      img.className = 'im-link-img'; img.alt = ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer'; img.src = data.image;
      img.addEventListener('error', function () { img.remove(); card.classList.remove('has-image'); });
      card.insertBefore(img, card.firstChild);
      card.classList.add('has-image');
    }
    if (data.title && body && !card.querySelector('.im-link-title')) {
      var t = document.createElement('strong'); t.className = 'im-link-title'; t.textContent = data.title;
      body.insertBefore(t, card.querySelector('.im-link-url'));
    }
    if (data.summary && body && !card.querySelector('.im-link-summary')) {
      var s = document.createElement('span'); s.className = 'im-link-summary'; s.textContent = data.summary;
      body.insertBefore(s, card.querySelector('.im-link-url'));
    }
  }
  function next() {
    while (running < 2 && queue.length) {
      var card = queue.shift();
      running++;
      fetch('/' + exp + '/im/api/link-preview?url=' + encodeURIComponent(card.getAttribute('data-preview-url')), { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; })
        .then(function (data) { fill(this, data); running--; next(); }.bind(card));
    }
  }
  function scan() {
    document.querySelectorAll('.im-link-card[data-preview-pending]').forEach(function (card) {
      card.removeAttribute('data-preview-pending'); // asked once per card
      card.setAttribute('data-preview-asked', '1');
      queue.push(card);
    });
    next();
  }
  var timer = null;
  new MutationObserver(function () { clearTimeout(timer); timer = setTimeout(scan, 200); })
    .observe(document.body, { childList: true, subtree: true });
  scan();
})();
