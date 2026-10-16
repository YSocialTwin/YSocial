/* Y Social login: "cascade" scene and small form helpers.
   Hexagonal nodes echo the YSocial logo; colours come from the logo palette. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var tr = function (k, p) { return window.YI18n ? window.YI18n.t(k, p) : k; };
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- helpers del form (funzionano anche senza la scena) ---------- */
  var eye = $('yl-eye'), pass = $('yl-pass');
  if (eye && pass) {
    eye.addEventListener('click', function () {
      var hide = pass.type === 'password';
      pass.type = hide ? 'text' : 'password';
      eye.textContent = tr(hide ? 'login.hide' : 'login.show');
      eye.setAttribute('aria-label', tr(hide ? 'login.hide_password' : 'login.show_password'));
    });
  }
  var convT = 0;                       /* 1 = la rete converge verso il centro */
  var forms = document.querySelectorAll('form.yl-form');
  Array.prototype.forEach.call(forms, function (f) {
    f.addEventListener('submit', function () {
      var b = f.querySelector('.yl-btn');
      if (b) { b.classList.add('loading'); setTimeout(function () { b.disabled = true; }, 0); }
      convT = 1;
    });
  });
  var go = $('yl-go'), radios = document.querySelectorAll('.yl-xp input');
  if (go && radios.length) {
    var upd = function () {
      var on = document.querySelector('.yl-xp input:checked');
      go.disabled = !on;
      $('yl-go-t').textContent = on ? tr('login.continue_to', { name: on.getAttribute('data-name') }) : tr('login.continue_default');
    };
    Array.prototype.forEach.call(radios, function (r) { r.addEventListener('change', upd); });
    if (radios.length === 1) radios[0].checked = true;
    if (window.YI18n) { window.YI18n.ready.then(upd); } else { upd(); }
    var q = $('yl-q'), cards = $('yl-cards');
    if (cards) setTimeout(function () { cards.classList.add('ready'); }, 1500);
    if (q) q.addEventListener('input', function () {
      var s = q.value.toLowerCase();
      Array.prototype.forEach.call(document.querySelectorAll('.yl-xp'), function (x) {
        x.style.display = x.textContent.toLowerCase().indexOf(s) > -1 ? '' : 'none';
      });
    });
  }

  /* ---------- scena ---------- */
  var cv = $('yl-net');
  if (!cv || !cv.getContext) return;
  var calm = document.body.getAttribute('data-cascade') === 'off';
  var cx = cv.getContext('2d'), layer = $('yl-layer'), card = $('yl-card'), cascEl = $('yl-casc'), halo = $('yl-halo');
  var PAL = ['109,195,208', '137,132,205', '255,100,42', '182,224,232', '197,194,230'];
  var POSTS = [
    { n: 'Marta', h: '@marta_r', c: 0, t: 'Does the new recommender change what we actually see? #recsys #echochambers' },
    { n: 'Leo', h: '@leo_news', c: 1, t: 'Breaking: the story spreads faster than the fact-checks. #misinformation' },
    { n: 'Aisha', h: '@aisha_ds', c: 3, t: 'Day 1: 300 agents, no idea what will happen. #YSocial' },
    { n: 'Tom', h: '@tom_photo', c: 2, t: 'Sunset by the sea, vintage filter. Thoughts? #photo' },
    { n: 'Giada', h: '@giada_mod', c: 4, t: '12 posts flagged: is automatic moderation too strict? #moderation' },
    { n: 'Karim', h: '@karim_x', c: 0, t: 'Who follows whom? The network reorganizes around a few hubs. #networks' },
    { n: 'Elena', h: '@elena_ux', c: 1, t: 'More diverse opinions in the feed, more discussion? #polarization' },
    { n: 'Nico', h: '@nico_sim', c: 2, t: 'Third run with a different seed, surprisingly stable results. #repro' }
  ];
  var W, H, D = Math.min(window.devicePixelRatio || 1, 2);
  var nodes = [], scr = [], pulses = [], rings = [], posts = [], casc = null;
  var now = 0, nextCasc = 600, nextAmb = 600, pi = Math.floor(Math.random() * POSTS.length), conv = 0;
  var mouse = { x: -999, y: -999 };

  function rnd(n) { return Math.floor(Math.random() * n); }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function col(c, a) { return 'rgba(' + PAL[c % 5] + ',' + a + ')'; }
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
  function fmt(s) { return esc(s).replace(/#\w+/g, '<span class="yl-tag">$&</span>'); }

  function init() {
    W = innerWidth; H = innerHeight;
    cv.width = W * D; cv.height = H * D; cx.setTransform(D, 0, 0, D, 0, 0);
    var n = clamp(Math.round(W * H / 15000), 30, 110), seeds = [], k, i;
    for (k = 0; k < 5; k++) seeds.push([Math.random() * W, Math.random() * H]);
    nodes = []; pulses = []; rings = []; posts = []; casc = null; layer.innerHTML = '';
    for (i = 0; i < n; i++) {
      var x = Math.random() * W, y = Math.random() * H, best = 0, bd = 1e9;
      for (k = 0; k < 5; k++) { var d = Math.hypot(x - seeds[k][0], y - seeds[k][1]); if (d < bd) { bd = d; best = k; } }
      nodes.push({ x: x, y: y, vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25,
        r: 2.4 + Math.random() * 2.4, c: best, glow: 0, cl: 0, cc: 0 });
    }
    scr = nodes.map(function () { return { x: 0, y: 0 }; });
    nextCasc = now + 600;
  }
  function hex(x, y, r) {
    cx.beginPath();
    for (var k = 0; k < 6; k++) {
      var a = Math.PI / 3 * k, px = x + r * Math.cos(a), py = y + r * Math.sin(a);
      if (k) cx.lineTo(px, py); else cx.moveTo(px, py);
    }
    cx.closePath();
  }
  function nb(i) {
    var o = [], a = scr[i];
    for (var j = 0; j < scr.length; j++) if (j !== i && Math.hypot(a.x - scr[j].x, a.y - scr[j].y) < 150) o.push(j);
    return o;
  }
  function pickNode() {
    var r = card.getBoundingClientRect();
    for (var k = 0; k < 40; k++) {
      var i = rnd(nodes.length), s = scr[i];
      if (s.x < 20 || s.x > W - 244 || s.y < 30 || s.y > H - 110) continue;
      var x0 = s.x + 14, y0 = s.y - 20;
      if (x0 + 224 < r.left - 8 || x0 > r.right + 8 || y0 + 90 < r.top || y0 > r.bottom) return i;
    }
    return rnd(nodes.length);
  }

  /* post di origine */
  function addPost(i, life) {
    if (W < 760) return;                                   /* su telefono la card copre tutto */
    var p = POSTS[pi++ % POSTS.length], el = document.createElement('div'), likes = rnd(20);
    el.className = 'yl-post';
    el.innerHTML = '<div class="yl-pa" style="background:var(--c' + p.c + ')">' + p.n[0] + '</div><div><div class="yl-who">' + p.n +
      '<span>' + p.h + '</span></div><p></p><div class="yl-act"><span>💬 ' + rnd(6) + '</span><span class="lk">♥ ' + likes + '</span></div></div>';
    layer.appendChild(el);
    var pe = el.querySelector('p');
    if (!reduce) {
      var k = 0;
      (function ty() {
        if (!el.isConnected) return;
        k += 2;
        if (k >= p.t.length) { pe.innerHTML = fmt(p.t); return; }
        pe.textContent = p.t.slice(0, k) + '▍'; setTimeout(ty, 26);
      })();
    } else pe.innerHTML = fmt(p.t);
    requestAnimationFrame(function () { el.classList.add('show'); });
    posts.push({ i: i, el: el, born: now, life: life, lk: el.querySelector('.lk'), n: likes, nextLike: now + 1200 });
  }
  function emoji(x, y) {
    var el = document.createElement('span');
    el.className = 'yl-emo'; el.textContent = ['♥', '🔥', '👍', '💬'][rnd(4)];
    el.style.left = x + 'px'; el.style.top = y + 'px'; el.style.setProperty('--dx', (rnd(30) - 10) + 'px');
    layer.appendChild(el); el.onanimationend = function () { el.remove(); };
  }

  /* cascata */
  function counter() {
    cascEl.innerHTML = '<b>' + casc.count + '</b> ' + YI18n.t('reshares ·') + ' <b>' + Math.round(casc.reached / nodes.length * 100) + '%</b> ' + YI18n.t('of the network reached');
  }
  function startCascade() {
    var src = pickNode(), dist = nodes.map(function () { return -1; }), par = [], levels = [[src]], cur = [src];
    dist[src] = 0;
    while (cur.length && levels.length < 10) {
      var nx = [];
      cur.forEach(function (u) { nb(u).forEach(function (v) { if (dist[v] < 0) { dist[v] = dist[u] + 1; par[v] = u; nx.push(v); } }); });
      if (nx.length) levels.push(nx);
      cur = nx;
    }
    casc = { levels: levels, par: par, start: now, fired: 0, cc: rnd(5), count: 0, reached: 0, end: 0 };
    addPost(src, 6200); counter();
  }
  function stepCascade() {
    var k = Math.floor((now - casc.start - 700) / 380);
    while (casc.fired <= k && casc.fired < casc.levels.length) {
      var lv = casc.levels[casc.fired], next = casc.levels[casc.fired + 1] || [];
      lv.forEach(function (v) {
        var n = nodes[v]; n.cl = 1; n.cc = casc.cc; n.glow = 1; rings.push({ i: v, t0: now, c: casc.cc });
        casc.reached++; casc.count += 1 + rnd(3);
        next.forEach(function (c) { if (casc.par[c] === v) pulses.push({ a: v, b: c, t: 0, c: casc.cc, sp: .045 }); });
      });
      casc.fired++; counter();
    }
    if (casc.fired >= casc.levels.length) {
      if (!casc.end) casc.end = now;
      else if (now - casc.end > 3600) { casc = null; nextCasc = now + 700; }
    }
  }

  addEventListener('resize', init);
  addEventListener('mousemove', function (e) {
    mouse.x = e.clientX; mouse.y = e.clientY;
    halo.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)';
  });

  function frame(ts) {
    now = ts; requestAnimationFrame(frame);
    conv += (convT - conv) * .07;
    cx.clearRect(0, 0, W, H);
    var i, j, a, b, d, n, s, pairs = [];
    for (i = 0; i < nodes.length; i++) {
      n = nodes[i];
      if (!reduce) {
        var dx = mouse.x - n.x, dy = mouse.y - n.y, m = Math.hypot(dx, dy);
        if (m < 170 && m > 1) { n.vx += dx / m * .012; n.vy += dy / m * .012; }
        n.vx = clamp(n.vx * .998, -.55, .55); n.vy = clamp(n.vy * .998, -.55, .55);
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > W) n.vx *= -1;
        if (n.y < 0 || n.y > H) n.vy *= -1;
      }
      s = scr[i]; s.x = n.x + (W / 2 - n.x) * conv * .65; s.y = n.y + (H / 2 - n.y) * conv * .65;
      n.glow *= .94; n.cl *= .9975;
      var mm = Math.hypot(s.x - mouse.x, s.y - mouse.y);
      if (mm < 120) n.glow = Math.max(n.glow, 1 - mm / 120);
    }
    for (i = 0; i < nodes.length; i++) for (j = i + 1; j < nodes.length; j++) {
      a = scr[i]; b = scr[j]; d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < 150) pairs.push([i, j, d]);
    }
    cx.lineWidth = 1;
    pairs.forEach(function (p) {
      var A = scr[p[0]], B = scr[p[1]], na = nodes[p[0]], nb2 = nodes[p[1]], al = (1 - p[2] / 150) * .36, hot = Math.max(na.cl, nb2.cl);
      cx.strokeStyle = hot > .05 ? col((na.cl >= nb2.cl ? na : nb2).cc, Math.min(.9, al + hot * .5)) : col(na.c, al);
      cx.beginPath(); cx.moveTo(A.x, A.y); cx.lineTo(B.x, B.y); cx.stroke();
    });
    for (i = 0; i < nodes.length; i++) {
      n = nodes[i]; s = scr[i];
      var hot = n.cl > .03, cc = hot ? n.cc : n.c, r = n.r + n.glow * 3 + (hot ? n.cl * 2.5 : 0);
      cx.fillStyle = col(cc, Math.min(1, .5 + n.glow * .5 + (hot ? n.cl * .3 : 0)));
      hex(s.x, s.y, r); cx.fill();
      if (n.glow > .05) { cx.strokeStyle = col(cc, n.glow * .55); cx.lineWidth = 1.2; hex(s.x, s.y, r + 4 + 8 * (1 - n.glow)); cx.stroke(); cx.lineWidth = 1; }
    }
    for (i = rings.length - 1; i >= 0; i--) {
      var rg = rings[i], age = now - rg.t0;
      if (age > 800) { rings.splice(i, 1); continue; }
      cx.strokeStyle = col(rg.c, (1 - age / 800) * .6);
      hex(scr[rg.i].x, scr[rg.i].y, 8 + age / 800 * 58); cx.stroke();
    }
    for (i = pulses.length - 1; i >= 0; i--) {
      var pl = pulses[i]; a = scr[pl.a]; b = scr[pl.b]; pl.t += pl.sp || .025;
      cx.fillStyle = col(pl.c, .95); cx.shadowColor = col(pl.c, .9); cx.shadowBlur = 12;
      cx.beginPath(); cx.arc(a.x + (b.x - a.x) * pl.t, a.y + (b.y - a.y) * pl.t, 3, 0, 6.283); cx.fill(); cx.shadowBlur = 0;
      if (pl.t >= 1) { nodes[pl.b].glow = 1; pulses.splice(i, 1); }
    }
    if (!reduce) {
      if (calm) {
        if (now > nextAmb) {                                 /* calm mode: occasional pulses only */
          nextAmb = now + 900;
          var from = rnd(nodes.length), nbs = nb(from);
          if (nbs.length) pulses.push({ a: from, b: nbs[rnd(nbs.length)], t: 0, c: nodes[from].c });
        }
      } else {
        if (!casc && now > nextCasc) startCascade();
        if (casc) stepCascade();
      }
    }
    for (i = posts.length - 1; i >= 0; i--) {
      var o = posts[i], ag = now - o.born;
      if (ag > o.life) { o.el.remove(); posts.splice(i, 1); continue; }
      if (ag > o.life - 500) o.el.classList.add('out');
      var q = scr[o.i], ex = clamp(q.x + 14, 8, W - 236), ey = clamp(q.y - 20, 20, H - 120);
      o.el.style.transform = 'translate(' + ex + 'px,' + ey + 'px)';
      if (now > o.nextLike) {
        o.n += 1 + rnd(3); o.lk.textContent = '♥ ' + o.n; o.lk.className = 'lk liked'; o.nextLike = now + 1100;
        if (!reduce) emoji(ex + 160 + rnd(40), ey + 50);
      }
    }
  }
  init(); requestAnimationFrame(frame);
})();
