/* F8 (H6): the members a person ticked under "Also post on" (a World Simulation they are enrolled in).
   wsCrossposts() -> "forum,dating" (comma separated, empty when nothing is ticked, the box is absent or the post carries a
   link: link and image-link posts keep the direct path, which has no cross-post, so the box is hidden for them).
   wsCrosspostList() -> the same as an array; wsCrosspostReset() clears the ticks after a post. */
(function () {
  if (window.wsCrossposts) return;
  var LINK_FIELDS = '#link_post, #link-url, #image-url';  // microblogging link field, forum link and image-link fields
  function hasLink() {
    return Array.prototype.some.call(document.querySelectorAll(LINK_FIELDS), function (el) {
      return el.offsetParent !== null && String(el.value || '').trim() !== '';
    });
  }
  function sync() {
    var hide = hasLink();
    Array.prototype.forEach.call(document.querySelectorAll('[data-ws-crosspost]'), function (box) {
      box.style.display = hide ? 'none' : '';
    });
  }
  function list() {
    if (hasLink()) return [];
    return Array.prototype.map.call(document.querySelectorAll('input.ws-crosspost:checked'), function (el) { return el.value; });
  }
  document.addEventListener('input', sync);
  document.addEventListener('change', sync);
  window.wsCrosspostList = list;
  window.wsCrossposts = function () { return list().join(','); };
  window.wsCrosspostReset = function () {
    Array.prototype.forEach.call(document.querySelectorAll('input.ws-crosspost:checked'), function (el) { el.checked = false; });
  };
})();
