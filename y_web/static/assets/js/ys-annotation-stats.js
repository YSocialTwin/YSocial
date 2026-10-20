/* "Your annotations" box of the social frontends: live distributions of the user's own annotations.
   Loaded by templates/shared/annotation_side_boxes.html; reads the endpoint from #ys-annostats-box[data-api]. */
(function () {
  var box = document.getElementById('ys-annostats-box');
  if (!box) return;
  var api = box.getAttribute('data-api');
  var body = document.getElementById('ys-annostats-body');
  var busy = false, again = false;

  var GREEN = '#16a34a', GREY = '#9ca3af', RED = '#dc2626', ORANGE = '#ea580c', AMBER = '#ca8a04', BLUE = '#2563eb';
  var SENTIMENT_LABELS = {
    binary: { '-1': 'Negative', '1': 'Positive' },
    '3point': { '-1': 'Negative', '0': 'Neutral', '1': 'Positive' },
    '5point': { '-2': 'Very negative', '-1': 'Negative', '0': 'Neutral', '1': 'Positive', '2': 'Very positive' }
  };
  var TOX_ORDER = ['none', 'low', 'medium', 'high'];
  var TOX_COLOR = { none: GREEN, low: AMBER, medium: ORANGE, high: RED };

  function cap(s) { s = String(s); return s.charAt(0).toUpperCase() + s.slice(1); }
  function sentimentColor(v) { return v > 0 ? GREEN : (v < 0 ? RED : GREY); }
  function sentimentLabel(scale, v) {
    var set = SENTIMENT_LABELS[scale];
    if (set && set[String(Math.round(v))] && Math.round(v) === v) return set[String(v)];
    var n = Math.round(v * 100) / 100;
    return (n > 0 ? '+' : '') + n;
  }

  function group(title, items) {   // items: [{label, count, color?}]
    if (!items || !items.length) return null;
    var max = Math.max.apply(null, items.map(function (i) { return i.count; })) || 1;
    var g = document.createElement('div'); g.className = 'ys-stat-group';
    var h = document.createElement('h5'); h.textContent = title; g.appendChild(h);
    items.forEach(function (it) {
      var row = document.createElement('div'); row.className = 'ys-stat-row';
      var l = document.createElement('span'); l.className = 'l'; l.textContent = it.label; l.title = it.label;
      var bar = document.createElement('div'); bar.className = 'ys-stat-bar';
      var fill = document.createElement('i'); fill.style.width = Math.max(4, Math.round(100 * it.count / max)) + '%';
      if (it.color) fill.style.background = it.color;
      bar.appendChild(fill);
      var n = document.createElement('span'); n.className = 'n'; n.textContent = it.count;
      row.appendChild(l); row.appendChild(bar); row.appendChild(n);
      g.appendChild(row);
    });
    return g;
  }

  function kpi(value, label) {
    var k = document.createElement('div'); k.className = 'ys-kpi';
    var s = document.createElement('strong'); s.textContent = value;
    var t = document.createElement('span'); t.textContent = label;
    k.appendChild(s); k.appendChild(t);
    return k;
  }

  function empty(text) {
    body.textContent = '';
    var e = document.createElement('div'); e.className = 'ys-stat-empty';
    e.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
    e.appendChild(document.createTextNode(text));
    body.appendChild(e);
  }

  function render(d) {
    if (!d || !d.ok) { empty('Statistics are not available right now.'); return; }
    if (!d.total) { empty('You have not annotated anything yet. Use the "Annotate" button under a post or comment.'); return; }
    body.textContent = '';
    var kp = document.createElement('div'); kp.className = 'ys-kpis';
    kp.appendChild(kpi(d.total, 'Annotated')); kp.appendChild(kpi(d.posts, 'Posts')); kp.appendChild(kpi(d.comments, 'Comments'));
    body.appendChild(kp);
    var sentiment = (d.sentiment || []).map(function (i) {
      return { label: sentimentLabel(d.sentiment_scale, i.value), count: i.count, color: sentimentColor(i.value) };
    });
    var tox = (d.toxicity || []).slice().sort(function (a, b) {
      var ia = TOX_ORDER.indexOf(a.level), ib = TOX_ORDER.indexOf(b.level);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    }).map(function (i) { return { label: cap(i.level), count: i.count, color: TOX_COLOR[i.level] || GREY }; });
    var emotions = (d.emotions || []).map(function (i) { return { label: cap(i.label), count: i.count, color: BLUE }; });
    var topics = (d.topics || []).map(function (i) { return { label: i.label, count: i.count }; });
    [group('Sentiment', sentiment), group('Toxicity', tox), group('Emotions', emotions), group('Topics', topics)]
      .forEach(function (g) { if (g) body.appendChild(g); });
  }

  function refresh() {
    if (busy) { again = true; return; }
    busy = true;
    fetch(api, { credentials: 'same-origin' }).then(function (r) { return r.json(); })
      .then(render).catch(function () { render(null); })
      .then(function () { busy = false; if (again) { again = false; refresh(); } });
  }

  window.addEventListener('ys:annotation-saved', refresh);   // fired by the annotation add-on right after a save
  setInterval(function () { if (!document.hidden) refresh(); }, 60000);   // fallback (other tab, older add-on build)
  refresh();
})();
