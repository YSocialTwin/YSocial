// Viewpoint and time bar: account picker that searches by username (with the small picture), round slider.
(function () {
  "use strict";
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) { n.className = cls; } if (text) { n.textContent = text; } return n; }

  var form = document.querySelector(".dt-acc");
  if (form && window.fetch) {
    var input = form.querySelector(".dt-acc-input"), hidden = form.querySelector("[data-acc-id]");
    var list = form.querySelector(".dt-acc-list"), thumb = form.querySelector("[data-acc-thumb]");
    var url = form.getAttribute("data-accounts"), round = form.getAttribute("data-round");
    var items = [], at = -1, timer = null, seq = 0;

    function avatar(a) {
      var box = el("span", "dt-acc-av");
      if (a.photo) { var im = el("img"); im.src = a.photo; im.alt = ""; im.loading = "lazy"; box.appendChild(im); }
      else { var i = el("i", "", a.initials || "?"); i.style.setProperty("--dt-hue", a.hue); box.appendChild(i); }
      return box;
    }
    function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); at = -1; }
    function mark() {
      Array.prototype.forEach.call(list.children, function (li, k) { li.classList.toggle("is-on", k === at); li.setAttribute("aria-selected", k === at ? "true" : "false"); });
    }
    function choose(a) {
      hidden.value = a.id; input.value = a.username;
      thumb.textContent = ""; thumb.appendChild(avatar(a).firstChild);
      form.submit();
    }
    function render() {
      list.textContent = "";
      if (!items.length) { var none = el("li", "dt-acc-none", input.getAttribute("data-none") || "–"); none.setAttribute("aria-disabled", "true"); list.appendChild(none); }
      items.forEach(function (a, k) {
        var li = el("li", "dt-acc-opt"); li.setAttribute("role", "option");
        li.appendChild(avatar(a)); li.appendChild(el("span", "dt-acc-name", a.username));
        li.addEventListener("mousedown", function (e) { e.preventDefault(); choose(a); });
        li.addEventListener("mousemove", function () { at = k; mark(); });
        list.appendChild(li);
      });
      list.hidden = false; input.setAttribute("aria-expanded", "true"); mark();
    }
    function search() {
      var mine = ++seq;
      fetch(url + "?q=" + encodeURIComponent(input.value.trim()) + "&round=" + encodeURIComponent(round), { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : { accounts: [] }; })
        .then(function (d) { if (mine !== seq) { return; } items = d.accounts || []; at = items.length ? 0 : -1; render(); })
        .catch(function () {});
    }
    input.addEventListener("focus", function () { input.select(); search(); });
    input.addEventListener("input", function () { hidden.value = ""; clearTimeout(timer); timer = setTimeout(search, 140); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (list.hidden) { search(); return; }
        at = (at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % Math.max(items.length, 1); mark();
      } else if (e.key === "Enter") {
        if (!list.hidden && items[at]) { e.preventDefault(); choose(items[at]); }
      } else if (e.key === "Escape") { close(); }
    });
    input.addEventListener("blur", function () { setTimeout(close, 120); });
    form.addEventListener("submit", function (e) {
      if (!hidden.value) {  // typed an exact username and pressed Enter before the list answered
        var typed = input.value.trim().toLowerCase();
        var hit = items.filter(function (a) { return a.username.toLowerCase() === typed; })[0] || items[0];
        if (hit) { hidden.value = hit.id; } else if (typed) { hidden.value = input.value.trim(); }  // the server resolves names too
        if (!hidden.value) { e.preventDefault(); }
      }
    });
  }

  var slider = document.querySelector("[data-slider]");
  if (slider) {
    var label = document.querySelector(".dt-now");
    var go = function () {
      var u = new URL(location.href), latest = parseInt(slider.max, 10), v = parseInt(slider.value, 10);
      if (v >= latest) { u.searchParams.delete("round"); } else { u.searchParams.set("round", String(v)); }
      location.href = u.toString();
    };
    var tick = null;
    slider.addEventListener("input", function () { if (label) { label.style.opacity = ".5"; } clearTimeout(tick); tick = setTimeout(go, 450); });
    slider.addEventListener("change", function () { clearTimeout(tick); go(); });
  }
})();
