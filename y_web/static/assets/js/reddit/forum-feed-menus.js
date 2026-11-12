/* Feed toolbar menus: "Sort by" (drives the native #feed-type-select) and "View" (card / compact). */
(function () {
    "use strict";
    var VIEW_KEY = "ysocial.forum.feedView";
    var root = document.documentElement;

    function readView() {
        try { return window.localStorage.getItem(VIEW_KEY) === "compact" ? "compact" : "card"; }
        catch (e) { return "card"; }
    }
    function writeView(v) {
        try { window.localStorage.setItem(VIEW_KEY, v); } catch (e) { /* private mode */ }
    }
    function applyView(v) {
        root.classList.toggle("fr-view-compact", v === "compact");
        document.querySelectorAll("[data-fr-view]").forEach(function (b) {
            b.classList.toggle("is-active", b.getAttribute("data-fr-view") === v);
        });
        document.querySelectorAll("[data-fr-view-icon]").forEach(function (i) {
            i.className = "mdi " + (v === "compact" ? "mdi-view-headline" : "mdi-view-agenda-outline");
        });
    }
    function closeMenus(except) {
        document.querySelectorAll("[data-fr-menu].is-open").forEach(function (m) {
            if (m !== except) {
                m.classList.remove("is-open");
                var t = m.querySelector(".fr-menu-trigger");
                if (t) { t.setAttribute("aria-expanded", "false"); }
            }
        });
    }

    applyView(readView());

    document.addEventListener("click", function (ev) {
        var trigger = ev.target.closest(".fr-menu-trigger");
        if (trigger) {
            var menu = trigger.closest("[data-fr-menu]");
            var open = !menu.classList.contains("is-open");
            closeMenus(menu);
            menu.classList.toggle("is-open", open);
            trigger.setAttribute("aria-expanded", open ? "true" : "false");
            return;
        }
        var sort = ev.target.closest("[data-fr-sort]");
        if (sort) {
            var select = document.getElementById("feed-type-select");
            if (select) {
                select.value = sort.getAttribute("data-fr-sort");
                select.dispatchEvent(new Event("change", { bubbles: true }));
            }
            document.querySelectorAll("[data-fr-sort]").forEach(function (b) {
                b.classList.toggle("is-active", b === sort);
            });
            document.querySelectorAll("[data-fr-sort-label]").forEach(function (l) {
                l.textContent = sort.getAttribute("data-label");
            });
            closeMenus();
            return;
        }
        var view = ev.target.closest("[data-fr-view]");
        if (view) {
            var v = view.getAttribute("data-fr-view");
            writeView(v);
            applyView(v);
            closeMenus();
            return;
        }
        closeMenus();
    });
    document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") { closeMenus(); }
    });
})();
