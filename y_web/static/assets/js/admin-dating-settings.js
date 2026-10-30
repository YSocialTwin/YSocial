// Dating experiment settings: show only the parameters of the selected recommender.
(function () {
  "use strict";
  var sel = document.getElementById("recsys-default");
  if (!sel) return;
  function show() {
    document.querySelectorAll(".recsys-params").forEach(function (el) {
      el.style.display = el.dataset.model === sel.value ? "" : "none";
    });
  }
  sel.addEventListener("change", show);
  show();
})();
