// Your profile: tabs (kept in the address), character counter, live values, preview of the picture to add.
(function () {
  "use strict";
  var box = document.querySelector(".dt-me[data-tabs]");
  if (!box) { return; }
  var tabs = box.querySelectorAll("[data-tab]"), panels = box.querySelectorAll("[data-panel]");
  function open(name) {
    var found = false;
    tabs.forEach(function (t) { var on = t.getAttribute("data-tab") === name; if (on) { found = true; } t.classList.toggle("is-on", on); t.setAttribute("aria-selected", on ? "true" : "false"); });
    if (!found) { return; }
    panels.forEach(function (p) { p.hidden = p.getAttribute("data-panel") !== name; });
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () {
      var name = t.getAttribute("data-tab");
      open(name);
      try { history.replaceState(null, "", "#" + name); } catch (e) { /* no history */ }
    });
  });
  if (location.hash) { open(location.hash.slice(1)); }

  var area = document.querySelector("[data-counter]");
  if (area) {
    var out = document.getElementById(area.getAttribute("data-counter"));
    var upd = function () { if (out) { out.textContent = String(area.value.length); } };
    area.addEventListener("input", upd); upd();
  }
  document.querySelectorAll("[data-out]").forEach(function (r) {
    var o = document.getElementById(r.getAttribute("data-out"));
    r.addEventListener("input", function () { if (o) { o.textContent = r.value; } });
  });

  var file = document.getElementById("dt-photo-file");
  var drop = document.querySelector("[data-drop]");
  if (file && drop) {
    var img = drop.querySelector("[data-preview]"), text = drop.querySelector("[data-drop-text]");
    var show = function () {
      var f = file.files && file.files[0];
      if (!f || !window.FileReader) { return; }
      var rd = new FileReader();
      rd.onload = function () { img.src = rd.result; img.hidden = false; drop.classList.add("has-file"); if (text) { text.textContent = f.name; } };
      rd.readAsDataURL(f);
    };
    file.addEventListener("change", show);
    ["dragover", "dragenter"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("is-over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.remove("is-over"); }); });
    drop.addEventListener("drop", function (e) {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files.length) { file.files = e.dataTransfer.files; show(); }
    });
  }
})();
