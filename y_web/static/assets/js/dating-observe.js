// Discover as an account: filter the cards by decision and read one in a window (arrow keys move between cards).
(function () {
  "use strict";
  var grid = document.querySelector("[data-deck-grid]");
  if (!grid) { return; }
  var tiles = Array.prototype.slice.call(grid.querySelectorAll("[data-peek]"));

  var filter = document.querySelector("[data-deck-filter]");
  if (filter) {
    filter.addEventListener("click", function (e) {
      var b = e.target.closest("[data-f]");
      if (!b) { return; }
      var f = b.getAttribute("data-f");
      Array.prototype.forEach.call(filter.querySelectorAll("button"), function (x) { x.classList.toggle("is-on", x === b); });
      tiles.forEach(function (t) { t.hidden = f !== "all" && t.getAttribute("data-dec") !== f; });
    });
  }

  var box = document.getElementById("dt-peek");
  if (!box) { return; }
  var body = box.querySelector("[data-peek-body]"), at = 0, opener = null;
  function visible() { return tiles.filter(function (t) { return !t.hidden; }); }
  function show(i) {
    var list = visible();
    if (!list.length) { return; }
    at = (i + list.length) % list.length;
    var tpl = document.querySelector('[data-peek-tpl="' + list[at].getAttribute("data-peek") + '"]');
    body.textContent = "";
    if (tpl) { body.appendChild(tpl.content.cloneNode(true)); }
  }
  function open(t) { opener = t; at = visible().indexOf(t); show(at); box.hidden = false; box.querySelector("[data-peek-close]").focus(); }
  function close() { box.hidden = true; if (opener) { opener.focus(); } }
  tiles.forEach(function (t) { t.addEventListener("click", function () { open(t); }); });
  box.addEventListener("click", function (e) {
    if (e.target === box || e.target.hasAttribute("data-peek-close")) { close(); return; }
    var n = e.target.closest("[data-peek-nav]");
    if (n) { show(at + parseInt(n.getAttribute("data-peek-nav"), 10)); }
  });
  document.addEventListener("keydown", function (e) {
    if (box.hidden) { return; }
    if (e.key === "Escape") { close(); } else if (e.key === "ArrowLeft") { show(at - 1); } else if (e.key === "ArrowRight") { show(at + 1); }
  });
})();
