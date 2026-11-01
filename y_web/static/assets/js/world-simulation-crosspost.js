/* F8 (H6): the members a person ticked under "Also post on" (a World Simulation they are enrolled in).
   wsCrossposts() -> "forum,dating" (comma separated, empty when nothing is ticked or the box is absent).
   wsCrosspostList() -> the same as an array; wsCrosspostReset() clears the ticks after a post. */
(function () {
  if (window.wsCrossposts) return;
  function list() {
    return Array.prototype.map.call(document.querySelectorAll('input.ws-crosspost:checked'), function (el) { return el.value; });
  }
  window.wsCrosspostList = list;
  window.wsCrossposts = function () { return list().join(','); };
  window.wsCrosspostReset = function () {
    Array.prototype.forEach.call(document.querySelectorAll('input.ws-crosspost:checked'), function (el) { el.checked = false; });
  };
})();
