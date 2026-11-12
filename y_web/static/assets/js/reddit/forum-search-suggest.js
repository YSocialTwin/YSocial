/* Live search for the forum top bar: communities, people and posts while typing.
 * Debounced, cancels stale requests, typo tolerant on the server, keyboard navigable, remembers recent searches.
 * Prefixes: "y/" = communities only, "@" = people only. Enter without a highlighted row runs the full search. */
(function () {
    "use strict";
    var form = document.querySelector(".forum-nav-search");
    var input = document.getElementById("forum-nav-search-input");
    if (!form || !input) { return; }

    var expId = (form.getAttribute("action") || "").split("/")[1];
    var scopeLink = form.querySelector(".forum-nav-scope");
    var scope = "";
    if (scopeLink) {
        scope = (scopeLink.textContent || "").trim().replace(/^y\//i, "");
    }
    var RECENT_KEY = "ysocial.forum.searches." + expId;
    var panel = document.createElement("div");
    panel.className = "forum-search-panel";
    panel.setAttribute("role", "listbox");
    panel.hidden = true;
    form.appendChild(panel);

    var timer = null, ctrl = null, rows = [], active = -1;

    function loadRecent() {
        try { var r = JSON.parse(window.localStorage.getItem(RECENT_KEY) || "[]"); return Array.isArray(r) ? r : []; }
        catch (e) { return []; }
    }
    function saveRecent(q) {
        q = (q || "").trim();
        if (!q) { return; }
        var list = loadRecent().filter(function (x) { return x !== q; });
        list.unshift(q);
        try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6))); } catch (e) { /* ignore */ }
    }
    function clearRecent() {
        try { window.localStorage.removeItem(RECENT_KEY); } catch (e) { /* ignore */ }
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) { n.className = cls; }
        if (text !== undefined) { n.textContent = text; }
        return n;
    }
    function highlight(node, text, query) {
        var q = query.replace(/^y\//i, "").replace(/^@/, "").trim();
        var terms = q.split(/\s+/).filter(Boolean).map(function (t) { return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); });
        if (!terms.length) { node.textContent = text; return node; }
        var re = new RegExp("(" + terms.join("|") + ")", "ig");
        text.split(re).forEach(function (part, i) {
            if (i % 2 === 1) { node.appendChild(el("mark", "", part)); }
            else if (part) { node.appendChild(document.createTextNode(part)); }
        });
        return node;
    }

    function setActive(i) {
        active = i;
        rows.forEach(function (r, idx) { r.el.classList.toggle("is-active", idx === i); });
        if (rows[i]) { rows[i].el.scrollIntoView({ block: "nearest" }); }
    }
    function section(title) { panel.appendChild(el("div", "forum-search-title", title)); }
    function addRow(icon, build, action) {
        var a = el("a", "forum-search-row");
        a.setAttribute("role", "option");
        a.appendChild(el("i", "mdi " + icon));
        var body = el("span", "forum-search-body");
        build(body);
        a.appendChild(body);
        if (action.url) { a.href = action.url; }
        a.addEventListener("mousedown", function (ev) { ev.preventDefault(); });
        a.addEventListener("click", function (ev) {
            if (action.run) { ev.preventDefault(); action.run(); } else { saveRecent(input.value); }
        });
        panel.appendChild(a);
        rows.push({ el: a });
    }

    function renderRecent() {
        panel.textContent = ""; rows = []; active = -1;
        var recent = loadRecent();
        if (!recent.length) { panel.hidden = true; return; }
        var head = el("div", "forum-search-title");
        head.appendChild(el("span", "", tr("Recent searches")));
        var clear = el("button", "forum-search-clear", tr("Clear"));
        clear.type = "button";
        clear.addEventListener("mousedown", function (ev) { ev.preventDefault(); clearRecent(); renderRecent(); });
        head.appendChild(clear);
        panel.appendChild(head);
        recent.forEach(function (q) {
            addRow("mdi-history", function (b) { b.textContent = q; }, { run: function () { input.value = q; submit(); } });
        });
        panel.hidden = false;
    }

    function render(q, data) {
        panel.textContent = ""; rows = []; active = -1;
        if (data.communities.length) {
            section(tr("Communities"));
            data.communities.forEach(function (c) {
                addRow("mdi-account-group-outline", function (b) { b.appendChild(highlight(el("strong"), c.label, q)); }, { url: c.url });
            });
        }
        if (data.users.length) {
            section(tr("People"));
            data.users.forEach(function (u) {
                addRow("mdi-account-outline", function (b) {
                    b.appendChild(highlight(el("strong"), u.username, q));
                    if (u.is_page) { b.appendChild(el("small", "", tr("Community Page"))); }
                }, { url: u.url });
            });
        }
        if (data.posts.length) {
            section(tr("Posts"));
            data.posts.forEach(function (p) {
                addRow("mdi-text-box-outline", function (b) {
                    b.appendChild(highlight(el("strong"), p.title, q));
                    var meta = [p.community, p.author, p.score + " ↑"].filter(Boolean).join(" · ");
                    b.appendChild(el("small", "", meta));
                }, { url: p.url });
            });
        }
        addRow("mdi-magnify", function (b) {
            b.appendChild(document.createTextNode(tr("Search for") + " "));
            b.appendChild(el("strong", "", "“" + q + "”"));
        }, { run: submit });
        panel.hidden = false;
    }

    var LABELS = {};
    try { LABELS = JSON.parse(form.getAttribute("data-i18n") || "{}"); } catch (e) { LABELS = {}; }
    function tr(s) { return LABELS[s] || s; }

    function submit() {
        saveRecent(input.value);
        panel.hidden = true;
        form.submit();
    }

    function query() {
        var q = input.value.trim();
        if (q.length < 2 && !/^(y\/|@)/i.test(q)) {
            if (!q) { renderRecent(); } else { panel.hidden = true; }
            return;
        }
        if (ctrl) { ctrl.abort(); }
        ctrl = new AbortController();
        var params = new URLSearchParams({ q: q });
        if (scope) { params.set("community", scope); }
        fetch("/" + expId + "/api/forum_search?" + params.toString(), { credentials: "same-origin", signal: ctrl.signal })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(function (data) { if (input.value.trim() === q) { render(q, data); } })
            .catch(function () { /* aborted or offline: keep the previous list */ });
    }

    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(query, 180); });
    input.addEventListener("focus", function () { if (input.value.trim()) { query(); } else { renderRecent(); } });
    input.addEventListener("blur", function () { setTimeout(function () { panel.hidden = true; }, 120); });
    input.addEventListener("keydown", function (ev) {
        if (panel.hidden || !rows.length) { return; }
        if (ev.key === "ArrowDown") { ev.preventDefault(); setActive((active + 1) % rows.length); }
        else if (ev.key === "ArrowUp") { ev.preventDefault(); setActive((active - 1 + rows.length) % rows.length); }
        else if (ev.key === "Escape") { panel.hidden = true; }
        else if (ev.key === "Enter" && active >= 0) { ev.preventDefault(); rows[active].el.click(); }
    });
    form.addEventListener("submit", function () { saveRecent(input.value); });
    document.addEventListener("keydown", function (ev) {
        if (ev.key === "/" && !/^(input|textarea|select)$/i.test((ev.target.tagName || "")) && !ev.target.isContentEditable) {
            ev.preventDefault(); input.focus();
        }
    });
})();
