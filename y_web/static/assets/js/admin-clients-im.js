/* Chats by Topic editor of the instant messaging client form. */
(function () {
  var data = JSON.parse(document.getElementById('ys-data-clients-im').textContent);
  var topics = data.topics;
  var rows = document.getElementById('im-chat-rows');
  var add = document.getElementById('im-add-chat');
  var counter = 0;
  var T = data.T;
  function esc(text) { var d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
  function line(label, control, hint) {
    return '<div class="box-line' + (hint ? ' ys-hint-text' : '') + '"><span class="left">' + label + '</span><span class="right ys-w-70">' + control + (hint ? '<small>' + esc(hint) + '</small>' : '') + '</span></div>';
  }
  var empty = document.getElementById('im-chat-empty');
  function refreshEmpty() { if (empty) empty.style.display = rows.children.length ? 'none' : ''; }
  function addRow() {
    var i = counter++;
    var p = 'chat.' + i + '.';
    var box = document.createElement('div');
    box.className = 'box-content';
    box.style.cssText = 'border:1px solid #e5e7eb;border-radius:6px;margin-bottom:8px;padding:8px;';
    var checks = topics.map(function (t) {
      return '<label class="ys-flex-click" style="margin-right:12px"><input type="checkbox" name="' + p + 'topic.' + t.id + '" value="true"> <span>' + esc(t.name) + '</span></label>';
    }).join('');
    box.innerHTML =
      '<div class="ys-text-xs-meta" style="font-weight:600;margin-bottom:6px">' + esc(T.chat) + ' ' + (rows.children.length + 1) + '</div>' +
      line(T.title, '<input type="text" class="input" name="' + p + 'title">', T.h_title) +
      line(T.type, '<div class="select"><select name="' + p + 'type"><option value="channel">' + T.channel + '</option><option value="supergroup">' + T.supergroup + '</option><option value="group">' + T.group + '</option></select></div>', T.h_type) +
      line(T.visibility, '<div class="select"><select name="' + p + 'visibility"><option value="public">' + T.pub + '</option><option value="private">' + T.priv + '</option></select></div>', T.h_visibility) +
      line(T.topics, checks, T.h_topics) +
      line(T.popularity, '<input type="number" class="input" min="0" step="any" name="' + p + 'popularity" placeholder="1">', T.h_popularity) +
      line(T.owner, '<input type="text" class="input" name="' + p + 'owner">', T.h_owner) +
      line(T.discussion, '<input type="checkbox" name="' + p + 'discussion" value="true">', T.h_discussion) +
      '<button type="button" class="button is-solid grey-button">' + T.remove + '</button>';
    box.querySelector('button').addEventListener('click', function () { box.remove(); refreshEmpty(); });
    rows.appendChild(box);
    refreshEmpty();
  }
  if (add) add.addEventListener('click', addRow);

  /* Live preview of the hourly activity rates (default 0.04 for the hours left empty). */
  var canvas = document.getElementById('activity_rates_im');
  var DEFAULT_RATE = 0.04;
  var chart = null;
  function rates() {
    var out = [];
    for (var h = 0; h < 24; h++) {
      var input = document.querySelector('input[name="hourly_' + h + '"]');
      var v = input && input.value !== '' ? parseFloat(input.value) : DEFAULT_RATE;
      out.push((isNaN(v) ? DEFAULT_RATE : v) * 100);
    }
    return out;
  }
  function drawChart() {
    if (!canvas || typeof Chart === 'undefined') return;
    if (chart) { chart.data.datasets[0].data = rates(); chart.update(); return; }
    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: Array.from({length: 24}, function (_, i) { return String(i); }),
        datasets: [{ label: T.activity, data: rates(), backgroundColor: 'rgba(34, 197, 94, 0.6)', borderColor: 'rgba(34, 197, 94, 1)', borderWidth: 1, borderRadius: 4 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return T.active.replace('{pct}', c.parsed.y.toFixed(2) + '%'); } } } },
        scales: { y: { beginAtZero: true, suggestedMax: 10, ticks: { font: { size: 10 }, callback: function (v) { return v + '%'; } } }, x: { ticks: { font: { size: 9 } }, grid: { display: false } } }
      }
    });
  }
  if (canvas) {
    document.querySelectorAll('input[name^="hourly_"]').forEach(function (i) { i.addEventListener('input', drawChart); });
    var details = canvas.closest('details');
    if (details) details.addEventListener('toggle', function () { if (details.open) setTimeout(drawChart, 100); });
  }
})();
