/* Widgets of the dating client and experiment settings pages (IR-D-05).
 *
 * The page renders every setting from the schema of the runtime; this script gives life to the widgets that are not
 * plain inputs: sliders with their value, the 0-10 importance scale, the 24 hourly rates with a bar chart, tag lists
 * and the switch that shows the advanced settings. Every widget writes its value to a normal form control, so the
 * forms work (with the plain inputs) even if the script does not run. */
(function () {
  "use strict";

  function each(selector, fn, root) {
    Array.prototype.forEach.call((root || document).querySelectorAll(selector), fn);
  }

  // ------------------------------------------------------------------ sliders
  function initSlider(input) {
    var out = input.parentNode.querySelector(".dating-slider-value");
    function show() { if (out) { out.textContent = input.value; } }
    input.addEventListener("input", show);
    show();
  }

  // ------------------------------------------------------------------ importance scale (0-10)
  function initImportance(box) {
    var step = parseFloat(box.getAttribute("data-step")) || 0.05;
    var hidden = box.querySelector('input[type="hidden"]');
    var boxes = box.querySelectorAll(".number-box");
    function select(n) {
      Array.prototype.forEach.call(boxes, function (b) {
        b.classList.toggle("selected", parseInt(b.getAttribute("data-value"), 10) === n);
      });
    }
    var current = parseFloat(hidden.value);
    select(isNaN(current) ? -1 : Math.max(0, Math.min(10, Math.round(current / step))));
    Array.prototype.forEach.call(boxes, function (b) {
      b.addEventListener("click", function () {
        if (hidden.disabled) { return; }
        var n = parseInt(b.getAttribute("data-value"), 10);
        hidden.value = String(Math.round(n * step * 1000) / 1000);
        select(n);
      });
    });
  }

  // ------------------------------------------------------------------ hourly rates with a bar chart
  function initHourly(box) {
    var hidden = box.querySelector('input[type="hidden"]');
    var inputs = box.querySelectorAll("input[data-hour]");
    var canvas = box.querySelector("canvas");
    var values = (hidden.value || "").split(",").map(function (v) { return parseFloat(v); });
    var chart = null;
    Array.prototype.forEach.call(inputs, function (input, h) {
      input.value = isNaN(values[h]) ? "" : values[h];
    });
    function read() {
      return Array.prototype.map.call(inputs, function (input) {
        var v = parseFloat(input.value);
        return isNaN(v) ? 0 : v;
      });
    }
    function sync() {
      var data = read();
      hidden.value = data.join(", ");
      if (chart) { chart.data.datasets[0].data = data; chart.update("none"); }
    }
    if (window.Chart && canvas) {
      var labels = [];
      for (var h = 0; h < 24; h++) { labels.push(h + "h"); }
      chart = new window.Chart(canvas.getContext("2d"), {
        type: "bar",
        data: { labels: labels, datasets: [{ data: read(), backgroundColor: "#e0457b", borderRadius: 3 }] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true } }
        }
      });
    }
    Array.prototype.forEach.call(inputs, function (input) { input.addEventListener("input", sync); });
  }

  // ------------------------------------------------------------------ tag lists
  function initTaglist(box) {
    var hidden = box.querySelector('input[type="hidden"]');
    var tags = box.querySelector(".dating-taglist-tags");
    var addInput = box.querySelector(".dating-taglist-add input");
    var addButton = box.querySelector(".dating-taglist-add button");
    var options = [];
    var chosen = [];
    try { options = JSON.parse(box.getAttribute("data-options") || "[]"); } catch (e) { options = []; }
    try { chosen = JSON.parse(hidden.value || "[]"); } catch (e) { chosen = []; }
    if (!Array.isArray(chosen)) { chosen = []; }
    function render() {
      tags.innerHTML = "";
      var known = options.slice();
      chosen.forEach(function (c) { if (known.indexOf(c) < 0) { known.push(c); } });
      known.forEach(function (label) {
        var tag = document.createElement("span");
        tag.className = "profession-tag" + (chosen.indexOf(label) >= 0 ? "" : " inactive");
        tag.textContent = label;
        tag.addEventListener("click", function () {
          if (hidden.disabled) { return; }
          var i = chosen.indexOf(label);
          if (i >= 0) { chosen.splice(i, 1); } else { chosen.push(label); }
          render();
        });
        tags.appendChild(tag);
      });
      hidden.value = JSON.stringify(chosen);
    }
    function add() {
      var v = (addInput.value || "").trim();
      if (v && chosen.indexOf(v) < 0) { chosen.push(v); }
      addInput.value = "";
      render();
    }
    addButton.addEventListener("click", add);
    addInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); add(); } });
    render();
  }

  // ------------------------------------------------------------------ advanced settings
  function initAdvanced(toggle) {
    function apply() {
      each("[data-advanced]", function (el) { el.hidden = !toggle.checked; });
    }
    toggle.addEventListener("change", apply);
    apply();
  }

  document.addEventListener("DOMContentLoaded", function () {
    each("input[data-dating-slider]", initSlider);
    each(".dating-importance", initImportance);
    each("[data-hourly]", initHourly);
    each("[data-taglist]", initTaglist);
    var toggle = document.getElementById("dating-show-advanced");
    if (toggle) { initAdvanced(toggle); } else { each("[data-advanced]", function (el) { el.hidden = false; }); }
  });
})();
