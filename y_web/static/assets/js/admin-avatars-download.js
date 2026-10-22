/* Profile pictures download: progress, pause and resume (admin notifications page). */
(function () {
  var st = document.createElement('style');
  st.textContent = '#avatars-box [hidden]{display:none !important}';
  document.head.appendChild(st);
})();
(function () {
  var box = document.getElementById('avatars-box'); if (!box) return;
  var $ = function (id) { return document.getElementById(id); };
  var L = function (k) { return box.getAttribute('data-l-' + k) || ''; };
  var timer = null;
  function mb(n) { return (n / 1048576).toFixed(0); }
  function render(s) {
    var show = s.status && s.status !== 'ready';
    box.style.display = show ? '' : 'none';  // [hidden] loses against Bulma's .columns{display:flex}
    if (!show) { if (timer) { clearInterval(timer); timer = null; } return; }
    $('avatars-status').textContent = L(s.status);
    $('avatars-bar').value = s.percent || 0;
    var d = (s.percent || 0) + '%';
    if (s.total) d += ' · ' + mb(s.bytes) + ' / ' + mb(s.total) + ' MB';
    if (s.files) d += ' · ' + s.files + ' ' + L('images');
    if (s.status === 'failed' && s.error) d += ' · ' + s.error;
    $('avatars-detail').textContent = d;
    $('avatars-pause').hidden = s.status !== 'downloading';
    $('avatars-resume').hidden = s.status !== 'paused';
    $('avatars-retry').hidden = !(s.status === 'failed' || s.status === 'idle');
    $('avatars-retry').textContent = s.status === 'idle' ? L('start') : L('retry');
    $('avatars-bar').hidden = s.status === 'idle';
  }
  function fail(e) { if (window.console) console.error('avatars status', e); }
  function json(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }
  function poll() { fetch('/admin/avatars/status', { credentials: 'same-origin' }).then(json).then(render).catch(fail); }
  function act(a) { fetch('/admin/avatars/' + a, { method: 'POST', credentials: 'same-origin' }).then(json).then(render).catch(fail); }
  $('avatars-pause').addEventListener('click', function () { act('pause'); });
  $('avatars-resume').addEventListener('click', function () { act('resume'); });
  $('avatars-retry').addEventListener('click', function () { act('resume'); });
  poll(); timer = setInterval(poll, 2000);
  // a finished download hides the box; a late start is picked up on the next page load
})();
