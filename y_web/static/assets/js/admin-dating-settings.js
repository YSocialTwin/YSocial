// Dating experiment settings: tabs, the description of the selected recommender and its parameters.
(function () {
  "use strict";

  function initTabs() {
    var tabs = document.querySelectorAll(".dating-tab");
    var panels = document.querySelectorAll(".dating-tabpanel");
    if (!tabs.length) return;
    function open(name) {
      tabs.forEach(function (t) { t.classList.toggle("is-active", t.dataset.tab === name); });
      panels.forEach(function (p) { p.hidden = p.dataset.panel !== name; });
      try { history.replaceState(null, "", "#" + name); } catch (e) { /* ignore */ }
    }
    tabs.forEach(function (t) { t.addEventListener("click", function () { open(t.dataset.tab); }); });
    var wanted = (location.hash || "").replace("#", "");
    open(document.querySelector('.dating-tab[data-tab="' + wanted + '"]') ? wanted : tabs[0].dataset.tab);
    // a field that fails the browser check sits in a hidden tab: open it
    var form = document.getElementById("dating-settings-form");
    if (form) {
      form.addEventListener("invalid", function (e) {
        var panel = e.target.closest && e.target.closest(".dating-tabpanel");
        if (panel && panel.hidden) { open(panel.dataset.panel); }
      }, true);
    }
  }

  function initRecsys() {
    var sel = document.getElementById("recsys-default");
    if (!sel) return;
    var side = document.getElementById("dating-recsys-side");
    function show() {
      document.querySelectorAll(".recsys-params").forEach(function (el) {
        var on = el.dataset.model === sel.value;
        el.style.display = on ? "" : "none";
      });
      if (!side) return;
      var name = side.querySelector("[data-recsys-name]");
      if (name) name.textContent = sel.value;
      side.querySelectorAll("[data-recsys-info]").forEach(function (p) {
        p.hidden = p.getAttribute("data-recsys-info") !== sel.value;
      });
    }
    sel.addEventListener("change", show);
    show();
  }

  initTabs();
  initRecsys();
})();
