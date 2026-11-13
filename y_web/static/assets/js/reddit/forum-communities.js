/* Communities directory: smart live search, scope (all / mine), sort and type filters; grouped by initial when A-Z. */
(function () {
    "use strict";
    var root = document.getElementById("fr-directory");
    if (!root) { return; }
    var expId = root.getAttribute("data-exp-id");
    var L = {};
    try { L = JSON.parse(root.getAttribute("data-i18n") || "{}"); } catch (e) { L = {}; }
    var list = document.getElementById("fr-directory-list");
    var count = document.getElementById("fr-directory-count");
    var search = document.getElementById("fr-directory-search");
    var sort = document.getElementById("fr-directory-sort");
    var kind = document.getElementById("fr-directory-kind");
    var state = { scope: root.getAttribute("data-scope") === "mine" ? "mine" : "all" };
    var timer = null, ctrl = null;

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) { n.className = cls; }
        if (text !== undefined) { n.textContent = text; }
        return n;
    }

    function card(c) {
        var a = el("a", "fr-directory-item");
        a.href = c.url;
        var av = el("span", "fr-modal-avatar");
        av.appendChild(el("i", "mdi " + c.icon));
        var body = el("span", "fr-modal-rowbody");
        body.appendChild(el("strong", "", c.label));
        body.appendChild(el("small", "", c.posts + " " + L.posts + " · " + c.participants + " " + L.participants));
        a.appendChild(av);
        a.appendChild(body);
        if (c.joined) { a.appendChild(el("span", "fr-pill fr-pill-soft", L.joined)); }
        return a;
    }

    function render(data) {
        list.textContent = "";
        var items = data.communities || [];
        count.textContent = data.total + " " + L.count;
        if (!items.length) {
            list.appendChild(el("p", "fr-directory-empty", state.scope === "mine" && !search.value.trim() ? L.emptyMine : L.empty));
            return;
        }
        var grouped = sort.value === "az" && !search.value.trim();
        var letter = null, group = null;
        items.forEach(function (c) {
            if (grouped) {
                var l = c.slug.charAt(0).toUpperCase();
                if (l !== letter) {
                    letter = l;
                    list.appendChild(el("h2", "fr-directory-letter", l));
                    group = el("div", "fr-directory-group");
                    list.appendChild(group);
                }
                group.appendChild(card(c));
            } else {
                if (!group) { group = el("div", "fr-directory-group"); list.appendChild(group); }
                group.appendChild(card(c));
            }
        });
    }

    function load() {
        if (ctrl) { ctrl.abort(); }
        ctrl = new AbortController();
        var q = search.value.trim();
        var params = new URLSearchParams({ q: q, scope: state.scope, kind: kind.value, sort: q && sort.value === "az" ? "relevance" : sort.value });
        fetch("/" + expId + "/api/forum_communities?" + params.toString(), { credentials: "same-origin", signal: ctrl.signal })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(render)
            .catch(function () { /* aborted or offline */ });
        var url = new URL(window.location.href);
        url.searchParams.set("scope", state.scope);
        if (q) { url.searchParams.set("q", q); } else { url.searchParams.delete("q"); }
        window.history.replaceState(null, "", url.toString());
    }

    root.querySelectorAll(".fr-directory-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            state.scope = tab.getAttribute("data-scope");
            root.querySelectorAll(".fr-directory-tab").forEach(function (t) { t.classList.toggle("is-active", t === tab); });
            load();
        });
    });
    search.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 150); });
    sort.addEventListener("change", load);
    kind.addEventListener("change", load);
    if (state.scope === "mine") { sort.value = "joined"; }
    load();
})();
