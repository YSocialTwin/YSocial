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
  // live search: results are fetched as the visitor types or changes a filter
  var form = document.getElementById("dt-search");
  var results = document.getElementById("dt-results");
  if (form && results && window.fetch && window.URLSearchParams) {
    var timer = null, seq = 0;
    var run = function () {
      var qs = new URLSearchParams(new FormData(form));
      var mine = ++seq;
      results.classList.add("is-loading");
      fetch(form.getAttribute("data-partial") + "?" + qs.toString() + "&partial=1", { credentials: "same-origin" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) {
          if (mine !== seq) return;
          results.innerHTML = html;
          results.classList.remove("is-loading");
          safe(function () { history.replaceState(null, "", "?" + qs.toString()); });
        }).catch(function () { results.classList.remove("is-loading"); });
    };
    var later = function () { clearTimeout(timer); timer = setTimeout(run, 250); };
    form.addEventListener("input", later);
    form.addEventListener("change", run);
    form.addEventListener("submit", function (e) { e.preventDefault(); clearTimeout(timer); run(); });
    var reset = document.getElementById("dt-reset");
    if (reset) reset.addEventListener("click", function (e) {
      e.preventDefault(); form.reset();
      form.querySelectorAll("input[type=text],input[type=search],input[type=number]").forEach(function (i) { i.value = ""; });
      form.querySelectorAll("input[type=checkbox]").forEach(function (i) { i.checked = false; });
      run();
    });
  }
  // chat: start at the last message; Enter sends, Shift+Enter makes a new line
  var log = document.getElementById("dt-chat-log");
  if (log && !location.hash) {
    var last = log.lastElementChild;
    if (last && last.scrollIntoView) last.scrollIntoView({ block: "end" });
  }
  var text = document.getElementById("dt-text");
  if (text) text.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && text.form) {
      e.preventDefault();
      if (text.form.requestSubmit) text.form.requestSubmit();
    }
  });
})();
