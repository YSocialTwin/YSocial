/* Chats by Topic editor of the instant messaging client form. */
(function () {
  var data = JSON.parse(document.getElementById('ys-data-clients-im').textContent);
  var topics = data.topics;
  var rows = document.getElementById('im-chat-rows');
  var add = document.getElementById('im-add-chat');
  var counter = 0;
  var T = data.T;
  function esc(text) { var d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
  function line(label, control) {
    return '<div class="box-line"><span class="left">' + label + '</span><span class="right ys-w-70">' + control + '</span></div>';
  }
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
      line(T.title, '<input type="text" class="input" name="' + p + 'title">') +
      line(T.type, '<div class="select"><select name="' + p + 'type"><option value="channel">' + T.channel + '</option><option value="supergroup">' + T.supergroup + '</option><option value="group">' + T.group + '</option></select></div>') +
      line(T.visibility, '<div class="select"><select name="' + p + 'visibility"><option value="public">' + T.pub + '</option><option value="private">' + T.priv + '</option></select></div>') +
      line(T.topics, checks) +
      line(T.popularity, '<input type="number" class="input" min="0" step="any" name="' + p + 'popularity">') +
      line(T.owner, '<input type="text" class="input" name="' + p + 'owner">') +
      line(T.discussion, '<input type="checkbox" name="' + p + 'discussion" value="true">') +
      '<button type="button" class="button is-solid grey-button">' + T.remove + '</button>';
    box.querySelector('button').addEventListener('click', function () { box.remove(); });
    rows.appendChild(box);
  }
  if (add) add.addEventListener('click', addRow);
})();
