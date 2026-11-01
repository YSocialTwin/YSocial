/* F8 (H6) + P7: the members a person ticked under "Also post on" (a World Simulation they are enrolled in) and the text to post
   on each of them.
   wsCrossposts() -> "forum,dating" (comma separated, empty when nothing is ticked, the box is absent or the post carries a
   link: link and image-link posts keep the direct path, which has no cross-post, so the box is hidden for them).
   wsCrosspostList() -> the same as an array; wsCrosspostReset() clears the ticks and the texts after a post.
   wsCrosspostTexts() -> JSON {member: text} of the ticked members whose text the person edited (the others get the server's
   rule text; the server also cuts every text to the limit of the platform and ignores members that were not ticked). */
(function () {
  if (window.wsCrossposts) return;
  var LINK_FIELDS = '#link_post, #link-url, #image-url';  // microblogging link field, forum link and image-link fields
  // the field the person writes in, on each composer (microblogging and forum post, IM message, photo caption, dating story)
  var SOURCE_FIELDS = '#publish, #im-text, [data-photo-share-caption], #photo-share-caption, #ws-dating-story-text';
  function hasLink() {
    return Array.prototype.some.call(document.querySelectorAll(LINK_FIELDS), function (el) {
      return el.offsetParent !== null && String(el.value || '').trim() !== '';
    });
  }
  function sourceText() {
    var found = '';
    Array.prototype.some.call(document.querySelectorAll(SOURCE_FIELDS), function (el) {
      var v = String(el.value || '').trim();
      if (el.offsetParent !== null && v) { found = v; return true; }
      return false;
    });
    return found;
  }
  function box() { return document.querySelector('[data-ws-crosspost]'); }
  function editors() { return Array.prototype.slice.call(document.querySelectorAll('.ws-crosspost-edit')); }
  function editorOf(member) {
    return editors().filter(function (e) { return e.getAttribute('data-member') === member; })[0];
  }
  function sync() {
    var hide = hasLink();
    Array.prototype.forEach.call(document.querySelectorAll('[data-ws-crosspost]'), function (b) {
      b.style.display = hide ? 'none' : '';
    });
  }
  function list() {
    if (hasLink()) return [];
    return Array.prototype.map.call(document.querySelectorAll('input.ws-crosspost:checked'), function (el) { return el.value; });
  }
  function count(editor) {
    var ta = editor.querySelector('textarea'), c = editor.querySelector('.ws-crosspost-count');
    if (c) c.textContent = ta.value.length + (ta.maxLength > 0 ? ' / ' + ta.maxLength : '');
  }
  // prefill the texts that the person has not touched with the server's rule text for the current words
  var timer = null;
  function suggest() {
    var b = box();
    if (!b) return;
    var members = list().filter(function (m) {
      var e = editorOf(m);
      return e && e.querySelector('textarea').getAttribute('data-edited') !== '1';
    });
    if (!members.length) return;
    var q = new URLSearchParams();
    q.set('text', sourceText());
    members.forEach(function (m) { q.append('crosspost', m); });
    fetch('/' + b.getAttribute('data-ws-exp') + '/federation/crosspost_suggest?' + q.toString(), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { texts: {} }; })
      .then(function (d) {
        members.forEach(function (m) {
          var e = editorOf(m), s = (d.texts || {})[m];
          if (!e || !s) return;
          var ta = e.querySelector('textarea');
          if (ta.getAttribute('data-edited') === '1') return;
          ta.maxLength = s.limit;
          ta.value = s.text;
          count(e);
        });
      })
      .catch(function () { /* the server cuts and shapes the text anyway */ });
  }
  function later() { clearTimeout(timer); timer = setTimeout(suggest, 300); }
  function showEditors() {
    var ticked = list();
    editors().forEach(function (e) { e.hidden = ticked.indexOf(e.getAttribute('data-member')) < 0; });
  }
  document.addEventListener('input', function (ev) {
    var t = ev.target;
    if (t && t.classList && t.classList.contains('ws-crosspost-text')) {
      t.setAttribute('data-edited', t.value.trim() ? '1' : '0');  // an emptied text goes back to the rule text
      count(t.parentNode);
      if (!t.value.trim()) later();
      return;
    }
    sync();
    if (t && t.matches && t.matches(SOURCE_FIELDS)) later();
  });
  document.addEventListener('change', function (ev) {
    sync();
    if (ev.target && ev.target.classList && ev.target.classList.contains('ws-crosspost')) { showEditors(); later(); }
  });
  window.wsCrosspostList = list;
  window.wsCrossposts = function () { return list().join(','); };
  window.wsCrosspostTexts = function () {
    var out = {};
    list().forEach(function (m) {
      var e = editorOf(m), ta = e && e.querySelector('textarea');
      if (ta && ta.getAttribute('data-edited') === '1' && ta.value.trim()) out[m] = ta.value;
    });
    return Object.keys(out).length ? JSON.stringify(out) : '';
  };
  window.wsCrosspostReset = function () {
    Array.prototype.forEach.call(document.querySelectorAll('input.ws-crosspost:checked'), function (el) { el.checked = false; });
    editors().forEach(function (e) {
      e.hidden = true;
      var ta = e.querySelector('textarea');
      ta.value = ''; ta.setAttribute('data-edited', '0'); count(e);
    });
  };
})();
