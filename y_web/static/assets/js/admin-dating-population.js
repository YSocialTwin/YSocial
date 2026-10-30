/* Tag pickers of the Dating sections of the population form (IR-D-05).
 *
 * A picker (`.dating-weights`) offers its known values as tags (the same `profession-tag` look as the other
 * population fields): a click activates a tag, which then gets a weight; a free value can be added. The result is
 * written to the hidden input of the field as "label=weight, label=weight", the format the server parses. */
(function () {
  "use strict";

  function init(box) {
    var name = box.getAttribute("data-weights-for");
    var hidden = box.parentNode.querySelector('input[type="hidden"][name="' + name + '"]');
    var tags = box.querySelector(".dating-weights-tags");
    var rows = box.querySelector(".dating-weights-rows");
    var addInput = box.querySelector(".dating-weights-add input");
    var weights = {};
    var options = [];
    try { options = JSON.parse(box.getAttribute("data-options") || "[]"); } catch (e) { options = []; }

    function sync() {
      var parts = Object.keys(weights).map(function (k) {
        var w = weights[k];
        return k + "=" + (w === "" || w === null ? 1 : w);
      });
      hidden.value = parts.join(", ");
    }

    function render() {
      tags.innerHTML = "";
      var known = options.slice();
      Object.keys(weights).forEach(function (k) { if (known.indexOf(k) < 0) { known.push(k); } });
      known.forEach(function (label) {
        var tag = document.createElement("span");
        tag.className = "profession-tag" + (label in weights ? "" : " inactive");
        tag.textContent = label;
        tag.addEventListener("click", function () {
          if (label in weights) { delete weights[label]; } else { weights[label] = 1; }
          render();
        });
        tags.appendChild(tag);
      });
      rows.innerHTML = "";
      Object.keys(weights).forEach(function (label) {
        var row = document.createElement("div");
        row.className = "dating-weight-row";
        var text = document.createElement("span");
        text.textContent = label;
        var input = document.createElement("input");
        input.type = "number";
        input.className = "input";
        input.min = "0";
        input.step = "any";
        input.value = weights[label];
        input.addEventListener("input", function () { weights[label] = input.value; sync(); });
        row.appendChild(text);
        row.appendChild(input);
        rows.appendChild(row);
      });
      sync();
    }

    function add() {
      var value = (addInput.value || "").trim().replace(/[=,]/g, " ").trim();
      if (!value) { return; }
      weights[value] = 1;
      addInput.value = "";
      render();
    }

    box.querySelector(".dating-weights-add-btn").addEventListener("click", add);
    addInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); add(); }
    });
    render();
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll(".dating-weights"), init);
  });
})();
