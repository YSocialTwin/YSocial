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

    // expand/collapse a single post while the compact view is on
    function addExpandButtons(scope) {
        (scope || document).querySelectorAll(".reddit-post").forEach(function (post) {
            if (post.querySelector(".fr-expand-button")) { return; }
            var footer = post.querySelector(".content-wrap > div[style*='border-top'], .post-footer");
            if (!footer) { return; }
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "fr-expand-button";
            btn.setAttribute("aria-label", "Expand");
            var icon = document.createElement("i");
            icon.className = "mdi mdi-arrow-expand";
            btn.appendChild(icon);
            footer.insertBefore(btn, footer.firstChild);
        });
    }
    function watchFeed() {
        addExpandButtons(document);
        var container = document.getElementById("feed-container") || document.getElementById("posts-container");
        if (container && window.MutationObserver) {
            new MutationObserver(function () { addExpandButtons(container); }).observe(container, { childList: true, subtree: true });
        }
    }
    document.addEventListener("click", function (ev) {
        var btn = ev.target.closest(".fr-expand-button");
        if (!btn) { return; }
        ev.preventDefault();
        ev.stopPropagation();
        var post = btn.closest(".reddit-post");
        if (post) {
            var on = post.classList.toggle("fr-expanded");
            var icon = btn.querySelector("i");
            if (icon) { icon.className = "mdi " + (on ? "mdi-arrow-collapse" : "mdi-arrow-expand"); }
        }
    }, true);
    if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", watchFeed); } else { watchFeed(); }

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
