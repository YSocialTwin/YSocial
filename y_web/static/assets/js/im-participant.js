/* Instant messaging participant mode (plan 6.8): every action goes to /<exp>/im/act, which forwards it to the
   human gateway. A sent message is shown as pending; a refused one shows the reason and can be retried with the
   same client_action_id (the server deduplicates). No dependency. */
(function () {
  'use strict';
  var body = document.body;
  if (body.getAttribute('data-participant') !== '1') return;
  var url = body.getAttribute('data-act-url');
  var csrf = body.getAttribute('data-csrf');
  var toast = document.getElementById('im-toast');
  var pending = {};

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function say(text, bad) {
    if (!toast) return;
    toast.textContent = text;
    toast.className = 'im-toast' + (bad ? ' is-bad' : '');
    toast.hidden = false;
    clearTimeout(say.t);
    say.t = setTimeout(function () { toast.hidden = true; }, bad ? 8000 : 2500);
  }
  var strings = {};
  try { strings = JSON.parse(document.getElementById('im-i18n').textContent) || {}; } catch (e) { strings = {}; }
  function T(key) { return strings[key] || key; }
  var reasonKey = {
    interactions_disabled: 'disabled', not_running: 'not_running', round_closed: 'round_closed',
    unavailable: 'unavailable', not_allowed: 'not_allowed', not_visible: 'not_visible',
    rate_limited: 'rate_limited', csrf: 'csrf'
  };
  function explain(res) {
    var code = res && res.code;
    if (code && reasonKey[code]) return T(reasonKey[code]);
    if (/_disabled$/.test(code || '')) return T('disabled');
    return (res && (res.message || res.code)) ? (res.message || res.code) : T('refused');
  }

  /* Send with the same id on a retry, so a lost answer never produces a second message. */
  function act(payload, key) {
    var id = pending[key] || (pending[key] = uuid());
    payload.client_action_id = id;
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, code: 'unavailable' }; });
    }).then(function (res) {
      var outcome = res && res.data && res.data.outcomes && res.data.outcomes[0];
      if (res && res.ok && outcome && outcome.ok) { delete pending[key]; return { ok: true }; }
      if (res && res.ok && outcome) { delete pending[key]; return { ok: false, code: outcome.code, message: outcome.reason }; }
      return { ok: false, code: res && res.code, message: res && res.message };
    }).catch(function () { return { ok: false, code: 'unavailable' }; });
  }

  function done(r, okText) {
    if (r.ok) { say(okText || ''); setTimeout(function () { location.reload(); }, 400); }
    else say(explain(r), true);
  }

  var composer = document.getElementById('im-composer');
  var replying = null;
  var banner = document.getElementById('im-replying');
  function setReply(id, who) {
    replying = id;
    if (!banner) return;
    banner.hidden = !id;
    banner.textContent = id ? T('replying_to') + ' ' + who + ' (' + T('cancel') + ')' : '';
  }
  if (banner) banner.addEventListener('click', function () { setReply(null); });

  if (composer) {
    composer.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var box = composer.querySelector('textarea');
      var text = box.value.trim();
      if (!text) return;
      var button = composer.querySelector('button[type=submit]');
      var payload = { type: replying ? 'reply' : 'post', chat_id: composer.getAttribute('data-chat'), text: text };
      if (replying) payload.reply_to_message_id = replying;
      if (composer.getAttribute('data-topic')) payload.forum_topic_id = parseInt(composer.getAttribute('data-topic'), 10);
      var key = 'send|' + payload.type + '|' + (replying || '') + '|' + text;
      button.disabled = true;
      var ghost = document.createElement('p');
      ghost.className = 'im-pending';
      ghost.textContent = text + ' (' + T('sending') + ')';
      var list = document.getElementById('im-messages');
      if (list) list.appendChild(ghost);
      act(payload, key).then(function (r) {
        button.disabled = false;
        if (r.ok) { box.value = ''; setReply(null); done(r); }
        else { ghost.textContent = text + ' (' + T('not_sent') + ': ' + explain(r) + ' - ' + T('retry') + ')'; ghost.className = 'im-pending is-bad'; say(explain(r), true); }
      });
    });
  }

  var joinForm = document.getElementById('im-join');
  if (joinForm) {
    joinForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var chat = joinForm.querySelector('[name=chat_id]').value.trim();
      var inv = joinForm.querySelector('[name=invite_id]').value.trim();
      var payload = { type: 'join', chat_id: chat };
      if (inv) payload.invite_id = inv;
      act(payload, 'join|' + chat + '|' + inv).then(function (r) {
        if (r.ok) { location.href = '/' + body.getAttribute('data-exp') + '/im/chat/' + encodeURIComponent(chat); } else say(explain(r), true);
      });
    });
  }

  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-im-do]');
    if (!el) return;
    var what = el.getAttribute('data-im-do');
    var msg = el.getAttribute('data-message');
    var chat = el.getAttribute('data-chat');
    if (what === 'reply') { setReply(msg, el.getAttribute('data-author') || ''); var t = document.getElementById('im-text'); if (t) t.focus(); return; }
    if (what === 'react') return act({ type: 'react', message_id: msg, emoji: el.getAttribute('data-emoji') }, 'react|' + msg + '|' + el.getAttribute('data-emoji') + '|' + Date.now()).then(function (r) { done(r); });
    if (what === 'delete') { if (!window.confirm(T('delete_confirm'))) return; return act({ type: 'delete', message_id: msg }, 'delete|' + msg).then(function (r) { done(r); }); }
    if (what === 'edit') {
      var text = window.prompt(T('edit_prompt'), el.getAttribute('data-text') || '');
      if (text === null || !text.trim()) return;
      return act({ type: 'edit', message_id: msg, text: text.trim() }, 'edit|' + msg + '|' + text).then(function (r) { done(r); });
    }
    if (what === 'forward') {
      var target = window.prompt(T('forward_prompt'));
      if (!target) return;
      return act({ type: 'forward', chat_id: target.trim(), forward_of_message_id: msg }, 'fwd|' + msg + '|' + target).then(function (r) { done(r); });
    }
    if (what === 'join' || what === 'leave') return act({ type: what, chat_id: chat }, what + '|' + chat + '|' + Date.now()).then(function (r) { done(r); });
    if (what === 'invite') {
      return fetch('/' + body.getAttribute('data-exp') + '/im/invite', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ chat_id: chat })
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (res.ok) window.prompt(T('invite_title'), JSON.stringify(res.data)); else say(explain(res), true);
      }).catch(function () { say(T('unavailable'), true); });
    }
  });

  /* Mark the chat as read once it is open. */
  var conv = document.querySelector('.im-conversation');
  if (conv && body.getAttribute('data-writable') === '1' && composer) {
    act({ type: 'read', chat_id: composer.getAttribute('data-chat') }, 'read|' + composer.getAttribute('data-chat') + '|' + Date.now());
  }

  /* "Connection lost" indicator: poll the gateway at the experiment's interval. */
  var conn = document.getElementById('im-conn');
  var gw = body.getAttribute('data-gateway-url');
  var every = Math.max(1, parseInt(body.getAttribute('data-poll') || '5', 10)) * 1000 || 5000;
  if (conn && gw) {
    setInterval(function () {
      if (document.hidden) return;
      fetch(gw, { credentials: 'same-origin' }).then(function (r) { return r.json(); })
        .then(function (s) { conn.hidden = !!(s && s.online); })
        .catch(function () { conn.hidden = false; });
    }, Math.max(every, 5000));
  }
})();
