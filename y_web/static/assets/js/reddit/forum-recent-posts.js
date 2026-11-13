/* "Recent posts": threads the user opened recently, kept in localStorage per experiment.
 * Thread page records an entry; the feed's right column renders the list and handles "Clear". */
(function () {
    "use strict";
    var MAX = 10;

    function keyFor(exp) { return "ysocial.forum.recent." + exp; }
    function load(exp) {
        try {
            var data = JSON.parse(window.localStorage.getItem(keyFor(exp)) || "[]");
            return Array.isArray(data) ? data : [];
        } catch (e) { return []; }
    }
    function save(exp, list) {
        try { window.localStorage.setItem(keyFor(exp), JSON.stringify(list.slice(0, MAX))); } catch (e) { /* storage blocked */ }
    }

    function record() {
        var holder = document.getElementById("fr-recent-entry");
        if (!holder) { return; }
        var exp = holder.getAttribute("data-exp-id");
        var entry;
        try { entry = JSON.parse(holder.getAttribute("data-entry")); } catch (e) { return; }
        if (!entry || !entry.id || !entry.title) { return; }
        entry.comments = document.querySelectorAll(".fr-comment").length;
        entry.url = "/" + exp + "/rthread/" + entry.id;
        var list = load(exp).filter(function (e) { return e.id !== entry.id; });
        list.unshift(entry);
        save(exp, list);
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) { n.className = cls; }
        if (text !== undefined) { n.textContent = text; }
        return n;
    }

    function render() {
        var box = document.getElementById("fr-recent");
        if (!box) { return; }
        var exp = box.getAttribute("data-exp-id");
        var list = load(exp);
        var ol = document.getElementById("fr-recent-list");
        ol.textContent = "";
        box.hidden = list.length === 0;
        list.forEach(function (e) {
            var li = el("li", "fr-recent-item");
            var meta = el("div", "fr-recent-meta");
            if (e.community) { meta.appendChild(el("strong", "", e.community)); }
            if (e.time) { meta.appendChild(el("span", "", (e.community ? "· " : "") + e.time)); }
            var a = el("a", "fr-recent-title", e.title);
            a.href = e.url;
            var stats = el("div", "fr-recent-stats", e.score + " ↑ · " + (e.comments || 0) + " ✉");
            li.appendChild(meta); li.appendChild(a); li.appendChild(stats);
            ol.appendChild(li);
        });
    }

    document.addEventListener("click", function (ev) {
        if (ev.target.closest("[data-fr-recent-clear]")) {
            var box = document.getElementById("fr-recent");
            if (box) { save(box.getAttribute("data-exp-id"), []); render(); }
        }
    });
    record();
    render();
})();
