// Dating profile page: cards that fade in as they come into view, and a photo lightbox with the caption.
(function () {
  "use strict";

  function reveal() {
    var items = document.querySelectorAll(".dt-reveal");
    if (!("IntersectionObserver" in window)) {
      items.forEach(function (el) { el.classList.add("is-in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.08 });
    items.forEach(function (el) { io.observe(el); });
  }

  function lightbox() {
    var box = document.getElementById("dt-lightbox");
    var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-lightbox]"));
    if (!box || !buttons.length) { return; }
    var img = box.querySelector("img");
    var cap = box.querySelector("figcaption");
    var index = 0;
    var opener = null;
    function show(i) {
      index = (i + buttons.length) % buttons.length;
      var b = buttons[index];
      img.src = b.getAttribute("data-lightbox");
      img.alt = b.getAttribute("data-caption") || "";
      cap.textContent = b.getAttribute("data-caption") || "";
    }
    function open(i, from) { opener = from; show(i); box.hidden = false; box.querySelector("[data-lb=close]").focus(); }
    function close() { box.hidden = true; if (opener) { opener.focus(); } }
    buttons.forEach(function (b, i) { b.addEventListener("click", function () { open(i, b); }); });
    box.addEventListener("click", function (e) {
      var act = e.target.getAttribute && e.target.getAttribute("data-lb");
      if (act === "close" || e.target === box) { close(); }
      else if (act === "prev") { show(index - 1); }
      else if (act === "next") { show(index + 1); }
    });
    document.addEventListener("keydown", function (e) {
      if (box.hidden) { return; }
      if (e.key === "Escape") { close(); }
      else if (e.key === "ArrowLeft") { show(index - 1); }
      else if (e.key === "ArrowRight") { show(index + 1); }
    });
  }

  // gallery: scroll-snap track with arrows, dots and thumbnails kept in step
  function gallery() {
    var g = document.querySelector("[data-gallery]");
    var track = g && g.querySelector("[data-track]");
    if (!track) { return; }
    var slides = track.children, dots = g.querySelectorAll("[data-dots] i");
    var thumbs = document.querySelectorAll("[data-thumb]"), cap = g.querySelector("[data-cap]");
    var at = 0;
    function sync(i) {
      at = i;
      Array.prototype.forEach.call(dots, function (d, k) { d.classList.toggle("is-on", k === i); });
      Array.prototype.forEach.call(thumbs, function (t, k) { t.classList.toggle("is-on", k === i); });
      if (cap && slides[i]) { cap.textContent = slides[i].getAttribute("data-caption") || ""; }
    }
    function go(i) {
      i = (i + slides.length) % slides.length;
      track.scrollTo({ left: slides[i].offsetLeft - track.offsetLeft, behavior: "smooth" });
      sync(i);
    }
    var tick = null;
    track.addEventListener("scroll", function () {
      clearTimeout(tick);
      tick = setTimeout(function () { sync(Math.round(track.scrollLeft / Math.max(track.clientWidth, 1))); }, 60);
    });
    g.addEventListener("click", function (e) {
      var b = e.target.closest("[data-go]");
      if (b) { e.stopPropagation(); go(at + (b.getAttribute("data-go") === "next" ? 1 : -1)); }
    });
    thumbs.forEach(function (t) { t.addEventListener("click", function () { go(parseInt(t.getAttribute("data-thumb"), 10)); }); });
  }

  // researcher block: tabs, and the numbers count up when they come into view
  function research() {
    document.querySelectorAll("[data-tabs]").forEach(function (box) {
      var tabs = box.querySelectorAll("[data-tab]"), panels = box.querySelectorAll("[data-panel]");
      tabs.forEach(function (t) {
        t.addEventListener("click", function () {
          tabs.forEach(function (x) { x.classList.toggle("is-on", x === t); });
          panels.forEach(function (p) { p.hidden = p.getAttribute("data-panel") !== t.getAttribute("data-tab"); });
          count(box);
        });
      });
    });
    function count(root) {
      if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { return; }
      root.querySelectorAll("[data-count]").forEach(function (el) {
        var txt = el.textContent, to = parseInt(txt, 10);
        if (!/^\d+$/.test(txt.trim()) || !(to > 0) || el.offsetParent === null) { return; }
        var t0 = null;
        (function step(t) {
          t0 = t0 || t;
          var k = Math.min((t - t0) / 600, 1);
          el.textContent = String(Math.round(to * (1 - Math.pow(1 - k, 3))));
          if (k < 1) { requestAnimationFrame(step); } else { el.textContent = txt; }
        })(performance.now());
      });
    }
    var first = document.querySelector("[data-tabs]");
    if (first && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { count(first); io.disconnect(); } }); }, { threshold: 0.3 });
      io.observe(first);
    }
  }

  reveal();
  gallery();
  research();
  lightbox();
})();
