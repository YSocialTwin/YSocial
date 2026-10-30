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

  // ------------------------------------------------------------------ duration (same controls as the other clients)
  function initDuration() {
    var display = document.getElementById("days_display");
    var hidden = document.getElementById("days_input");
    var infinite = document.getElementById("infinite_duration");
    if (!display || !hidden) { return; }
    function sync() { hidden.value = display.value; }
    display.addEventListener("input", sync);
    display.addEventListener("change", sync);
    if (!infinite) { return; }
    infinite.addEventListener("change", function () {
      if (infinite.checked) {
        display.dataset.previousValue = display.value;
        display.value = "\u221e";
        display.disabled = true;
        display.style.opacity = "0.5";
        hidden.value = "-1";
      } else {
        display.value = display.dataset.previousValue || "30";
        display.disabled = false;
        display.style.opacity = "1";
        hidden.value = display.value;
      }
    });
  }

  // ------------------------------------------------------------------ models of the server (Fetch Models)
  var VISION_MARKERS = ["vision", "minicpm-v", "qwen-vl", "llava", "internvl", "pixtral", "molmo", "gpt-4o", "gpt-4.1", "omni", "-vl", "_vl"];
  function isVisionModel(name) {
    var lowered = String(name || "").toLowerCase();
    return VISION_MARKERS.some(function (m) { return lowered.indexOf(m) >= 0; });
  }
  function tr(text, params) {
    return window.YI18n && window.YI18n.t ? window.YI18n.t(text, params) : text;
  }
  function setStatus(id, html, ms) {
    var el = document.querySelector('[data-fetch-status="' + id + '"]');
    if (!el) { return; }
    el.innerHTML = html;
    if (ms) { setTimeout(function () { el.innerHTML = ""; }, ms); }
  }
  function fillSelect(select, models, placeholder) {
    var previous = select.value;
    select.innerHTML = "";
    var empty = document.createElement("option");
    empty.value = "";
    empty.textContent = placeholder;
    select.appendChild(empty);
    models.forEach(function (m) {
      var o = document.createElement("option");
      o.value = m;
      o.textContent = m;
      select.appendChild(o);
    });
    if (models.indexOf(previous) >= 0) { select.value = previous; }
    else if (placeholder === tr("Select a vision model") && models.length) { select.value = models[0]; }
    select.dispatchEvent(new Event("change"));
  }
  function fetchModels(targetId, onlyVision) {
    var urlInput = document.getElementById("dating_llm_url");
    var select = document.getElementById(targetId);
    var url = urlInput ? urlInput.value.trim() : "";
    if (!url || !select) {
      if (window.YNotify) { window.YNotify.warning(tr("Please enter an LLM server URL")); }
      return;
    }
    setStatus(targetId, '<i class="mdi mdi-loading mdi-spin"></i> ' + tr("Fetching..."));
    fetch("/admin/api/fetch_models?llm_url=" + encodeURIComponent(url))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error || !data.models) {
          setStatus(targetId, '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + (data.error || data.message || tr("Connection failed")) + "</span>", 5000);
          return;
        }
        var models = onlyVision ? data.models.filter(isVisionModel) : data.models;
        if (onlyVision && !models.length) {
          setStatus(targetId, '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + tr("No vision-capable models found on this server") + "</span>", 5000);
          return;
        }
        fillSelect(select, models, onlyVision ? tr("Select a vision model") : tr("Select a model"));
        var label = onlyVision ? "{length} vision models loaded" : "{length} models loaded";
        setStatus(targetId, '<span style="color: green;"><i class="mdi mdi-check"></i> ' + tr(label, { length: models.length }) + "</span>", 3000);
      })
      .catch(function () {
        setStatus(targetId, '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + tr("Connection failed") + "</span>", 5000);
      });
  }
  function initModels() {
    each("[data-fetch-models]", function (b) {
      b.addEventListener("click", function () { fetchModels(b.getAttribute("data-fetch-models"), false); });
    });
    each("[data-fetch-vision]", function (b) {
      b.addEventListener("click", function () { fetchModels(b.getAttribute("data-fetch-vision"), true); });
    });
    // the photos are shown to the model only when a vision model is chosen
    var vision = document.getElementById("dating_vision_model");
    var share = document.querySelector('input[type="checkbox"][name="adv__swipe__llm_vision"]');
    if (vision && share) {
      vision.addEventListener("change", function () { share.checked = !!vision.value; });
    }
    // the client is created once a language model is chosen
    var button = document.querySelector("button[data-requires-model]");
    var model = button ? document.getElementById(button.getAttribute("data-requires-model")) : null;
    if (button && model && !button.disabled) {
      var update = function () { button.disabled = !model.value; };
      model.addEventListener("change", update);
      update();
    }
  }

  // ------------------------------------------------------------------ image model: a short list or any model id
  function initDiffusion(select) {
    var box = select.closest(".dating-diffusion");
    var text = box && box.querySelector("[data-diffusion-text]");
    if (!text) { return; }
    select.addEventListener("change", function () {
      if (select.value === "__other__") { text.hidden = false; text.value = ""; text.focus(); }
      else { text.value = select.value; text.hidden = true; }
    });
  }

  // ------------------------------------------------------------------ recommender: what the chosen model does
  function initRecsys(select) {
    var side = document.getElementById("dating-recsys-side");
    var inline = document.querySelector(".dating-recsys-info");
    if (side && inline && !side.contains(inline)) {
      // the description of the chosen model lives in the side column, next to the form
      side.hidden = false;
      side.appendChild(inline);
    }
    function show() {
      each("[data-recsys-info]", function (p) { p.hidden = p.getAttribute("data-recsys-info") !== select.value; });
      var name = side && side.querySelector("[data-recsys-name]");
      if (name) { name.textContent = select.value || select.options[select.selectedIndex].text; }
    }
    select.addEventListener("change", show);
    show();
  }

  document.addEventListener("DOMContentLoaded", function () {
    initDuration();
    initModels();
    each("[data-recsys]", initRecsys);
    each("[data-diffusion-select]", initDiffusion);
    each("input[data-dating-slider]", initSlider);
    each(".dating-importance", initImportance);
    each("[data-hourly]", initHourly);
    each("[data-taglist]", initTaglist);
    var toggle = document.getElementById("dating-show-advanced");
    if (toggle) { initAdvanced(toggle); } else { each("[data-advanced]", function (el) { el.hidden = false; }); }
  });
})();
