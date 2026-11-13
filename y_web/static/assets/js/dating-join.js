(function () {
  "use strict";
  var form = document.getElementById("dt-join-form");
  if (!form) return;
  var steps = Array.prototype.slice.call(form.querySelectorAll(".dt-step"));
  var dots = Array.prototype.slice.call(document.querySelectorAll("#dt-steps li"));
  var fill = document.getElementById("dt-steps-fill");
  var back = document.getElementById("dt-back"), next = document.getElementById("dt-next"), submit = document.getElementById("dt-submit");
  var at = 0;
  form.classList.add("is-wizard"); // without this script every step stays visible and the form works as one page

  function show(i, dir) {
    at = Math.max(0, Math.min(steps.length - 1, i));
    steps.forEach(function (s, k) {
      s.classList.toggle("is-on", k === at);
      s.classList.toggle("from-left", dir < 0);
    });
    dots.forEach(function (d, k) { d.classList.toggle("is-on", k === at); d.classList.toggle("is-done", k < at); });
    if (fill) fill.style.width = (100 * (at + 1) / steps.length) + "%";
    back.hidden = at === 0;
    next.hidden = at === steps.length - 1;
    submit.hidden = at !== steps.length - 1;
    var first = steps[at].querySelector("input:not([type=hidden]):not([type=radio]), textarea");
    if (first && at > 0) first.focus({ preventScroll: true });
  }

  function valid() {
    var ok = true;
    Array.prototype.forEach.call(steps[at].querySelectorAll("input,textarea,select"), function (f) {
      var bad = !f.checkValidity();
      f.classList.toggle("is-bad", bad);
      if (bad) ok = false;
    });
    if (!ok) { var b = steps[at].querySelector(".is-bad"); if (b) b.focus(); steps[at].classList.remove("shake"); void steps[at].offsetWidth; steps[at].classList.add("shake"); }
    return ok;
  }

  next.addEventListener("click", function () { if (valid()) show(at + 1, 1); });
  back.addEventListener("click", function () { show(at - 1, -1); });
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA" && at < steps.length - 1) { e.preventDefault(); next.click(); }
  });
  form.addEventListener("input", function (e) { e.target.classList && e.target.classList.remove("is-bad"); });

  // chips that fill a text input (comma separated list, or a single value)
  Array.prototype.forEach.call(form.querySelectorAll(".dt-chips[data-fill]"), function (box) {
    var input = document.getElementById(box.getAttribute("data-fill"));
    var single = box.getAttribute("data-single") === "1";
    var list = function () { return input.value.split(",").map(function (x) { return x.trim(); }).filter(Boolean); };
    var sync = function () {
      var cur = list().map(function (x) { return x.toLowerCase(); });
      Array.prototype.forEach.call(box.querySelectorAll(".dt-tag"), function (b) {
        b.classList.toggle("is-on", cur.indexOf(b.getAttribute("data-value").toLowerCase()) >= 0);
      });
    };
    box.addEventListener("click", function (e) {
      var b = e.target.closest(".dt-tag");
      if (!b) return;
      var v = b.getAttribute("data-value");
      if (single) input.value = v;
      else {
        var cur = list(), i = cur.map(function (x) { return x.toLowerCase(); }).indexOf(v.toLowerCase());
        if (i >= 0) cur.splice(i, 1); else cur.push(v);
        input.value = cur.join(", ");
      }
      input.classList.remove("is-bad");
      sync();
    });
    input.addEventListener("input", sync);
    sync();
  });

  var dist = document.getElementById("dt-dist"), distOut = document.getElementById("dt-dist-out");
  if (dist && distOut) {
    var km = form.getAttribute("data-t-km") || "km";
    var upd = function () { distOut.textContent = dist.value + " " + km; };
    dist.addEventListener("input", upd); upd();
  }

  var bio = document.getElementById("dt-bio"), count = document.getElementById("dt-bio-count");
  if (bio && count) {
    var c = function () { count.textContent = bio.value.length + " / " + bio.maxLength; };
    bio.addEventListener("input", c); c();
  }

  // photo tiles: a preview of the chosen file
  Array.prototype.forEach.call(form.querySelectorAll(".dt-drop"), function (tile) {
    var input = tile.querySelector(".dt-drop-input"), img = tile.querySelector(".dt-drop-img"), zone = tile.querySelector(".dt-drop-zone");
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) { img.hidden = true; tile.classList.remove("has-file"); return; }
      var r = new FileReader();
      r.onload = function () { img.src = r.result; img.hidden = false; tile.classList.add("has-file"); };
      r.readAsDataURL(f);
    });
    ["dragenter", "dragover"].forEach(function (ev) { zone.addEventListener(ev, function (e) { e.preventDefault(); tile.classList.add("is-over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { zone.addEventListener(ev, function () { tile.classList.remove("is-over"); }); });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event("change")); }
    });
  });

  form.addEventListener("submit", function (e) {
    // a step that was skipped over by the keyboard: go back to the first invalid one
    for (var i = 0; i < steps.length; i++) {
      var bad = Array.prototype.some.call(steps[i].querySelectorAll("input,textarea,select"), function (f) { return !f.checkValidity(); });
      if (bad) { e.preventDefault(); show(i, i < at ? -1 : 1); valid(); return; }
    }
    submit.disabled = true;
    submit.classList.add("is-busy");
  });

  show(0, 1);
})();
