(function () {
  "use strict";
  var root = document.documentElement;
  function safe(fn) { try { return fn(); } catch (e) { return null; } }
  // theme: remembered when storage works, never required
  var saved = safe(function () { return localStorage.getItem("dt-theme"); });
  if (saved === "dark" || saved === "light") root.setAttribute("data-theme", saved);
  else if (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) root.setAttribute("data-theme", "dark");
  var tb = document.getElementById("dt-theme");
  if (tb) tb.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    safe(function () { localStorage.setItem("dt-theme", next); });
  });
  // deck: one card at a time, arrow keys
  var deck = document.getElementById("dt-deck");
  if (deck) {
    var slides = deck.querySelectorAll(".dt-slide"), i = 0;
    var counter = document.getElementById("dt-counter");
    var show = function (n) {
      i = Math.max(0, Math.min(slides.length - 1, n));
      slides.forEach(function (s, k) { s.hidden = k !== i; });
      if (counter) counter.textContent = (i + 1) + " / " + slides.length;
    };
    var p = document.getElementById("dt-prev"), nx = document.getElementById("dt-next");
    if (p) p.addEventListener("click", function () { show(i - 1); });
    if (nx) nx.addEventListener("click", function () { show(i + 1); });
    document.addEventListener("keydown", function (e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName)) return;
      if (e.key === "ArrowLeft") show(i - 1); else if (e.key === "ArrowRight") show(i + 1);
    });
  }
  // polling: tell the viewer that newer rounds exist, never reload by itself
  var poll = parseInt(document.body.getAttribute("data-poll") || "0", 10);
  var latest = parseInt(document.body.getAttribute("data-latest") || "0", 10);
  var url = document.body.getAttribute("data-status-url");
  if (poll > 0 && url && window.fetch) {
    setInterval(function () {
      fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (s) {
        if (s && s.latest_round > latest) { var b = document.getElementById("dt-live"); if (b) b.hidden = false; }
      }).catch(function () {});
    }, poll * 1000);
  }
})();
