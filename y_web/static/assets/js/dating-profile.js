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

  reveal();
  lightbox();
})();
