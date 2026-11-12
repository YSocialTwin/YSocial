/* Repost dialog: choose where to cross-post a thread (own profile or a community). */
(function () {
    "use strict";
    var modal = document.getElementById("fr-crosspost");
    if (!modal) { return; }
    var expId = modal.getAttribute("data-exp-id");
    var list = document.getElementById("fr-crosspost-list");
    var search = document.getElementById("fr-crosspost-search");
    var toast = document.getElementById("fr-toast");
    var L = {};
    try { L = JSON.parse(modal.getAttribute("data-i18n") || "{}"); } catch (e) { L = {}; }
    var current = { postId: null, community: "" };
    var platforms = null;  // other World Simulation platforms the person is enrolled on (null = not loaded yet)
    var PLATFORM_ICONS = { microblogging: "mdi-message-text-outline", forum: "mdi-forum-outline", photo_sharing: "mdi-camera-outline", instant_messaging: "mdi-send-outline", dating: "mdi-heart-outline" };
    var timer = null, ctrl = null, toastTimer = null;

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) { n.className = cls; }
        if (text !== undefined) { n.textContent = text; }
        return n;
    }
    function csrfHeaders() {
        var h = { "Content-Type": "application/json" };
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) { h["X-CSRFToken"] = meta.getAttribute("content"); }
        return h;
    }

    function showToast(text, href) {
        toast.textContent = "";
        toast.appendChild(document.createTextNode(text + " "));
        if (href) {
            var a = el("a", "", L.view || "View");
            a.href = href;
            toast.appendChild(a);
        }
        toast.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.hidden = true; }, 6000);
    }

    function row(iconClass, title, subtitle, onPick) {
        var li = el("li");
        var b = el("button", "fr-modal-row");
        b.type = "button";
        var av = el("span", "fr-modal-avatar");
        av.appendChild(el("i", "mdi " + iconClass));
        var body = el("span", "fr-modal-rowbody");
        body.appendChild(el("strong", "", title));
        if (subtitle) { body.appendChild(el("small", "", subtitle)); }
        b.appendChild(av); b.appendChild(body);
        b.appendChild(el("i", "mdi mdi-chevron-right fr-modal-chevron"));
        b.addEventListener("click", onPick);
        li.appendChild(b);
        list.appendChild(li);
    }

    function pick(slug, label) {
        fetch("/api/reddit/" + expId + "/crosspost", {
            method: "POST", credentials: "same-origin", headers: csrfHeaders(),
            body: JSON.stringify({ post_id: current.postId, community_slug: slug })
        }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
            .then(function (res) {
                if (!res.ok) { throw new Error(); }
                var data = res.body.data || res.body;
                close();
                showToast(data.created === false ? (L.already || "") : ((L.posted || "") + " " + label), data.url);
            })
            .catch(function () { showToast(L.error || "Unable to repost right now."); });
    }

    function pickPlatform(p) {
        fetch("/" + expId + "/federation/repost", {
            method: "POST", credentials: "same-origin", headers: csrfHeaders(),
            body: JSON.stringify({ members: [p.member], post_id: current.postId, community: current.community })
        }).then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(function () { close(); showToast((L.posted || "") + " " + p.label); })
            .catch(function () { showToast(L.error || "Unable to repost right now."); });
    }

    function renderPlatforms(q) {
        var shown = (platforms || []).filter(function (p) { return !q || String(p.label).toLowerCase().indexOf(q) >= 0; });
        if (!shown.length) { return; }
        list.appendChild(el("li", "fr-modal-section", L.platforms || ""));
        shown.forEach(function (p) {
            row(PLATFORM_ICONS[p.platform_type] || "mdi-link-variant", p.label, L.platformHint || "", function () { pickPlatform(p); });
        });
    }

    function loadPlatforms() {
        if (platforms !== null) { return Promise.resolve(); }
        return fetch("/" + expId + "/federation/repost_targets", { credentials: "same-origin" })
            .then(function (r) { return r.ok ? r.json() : { platforms: [] }; })
            .then(function (d) { platforms = d.platforms || []; })
            .catch(function () { platforms = []; });
    }

    function load() {
        if (ctrl) { ctrl.abort(); }
        ctrl = new AbortController();
        var params = new URLSearchParams({ q: search.value.trim(), exclude: current.community || "" });
        var signal = ctrl.signal;
        Promise.all([loadPlatforms(), fetch("/api/reddit/" + expId + "/crosspost/targets?" + params.toString(), { credentials: "same-origin", signal: signal })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })])
            .then(function (all) {
                var res = all[1];
                var data = res.data || res;
                list.textContent = "";
                if (data.profile) {
                    row("mdi-account-circle-outline", "u/" + data.profile.username, L.profile || "Your profile", function () { pick("", "u/" + data.profile.username); });
                }
                (data.communities || []).forEach(function (c) {
                    var sub = c.posts + " " + (L.posts || "posts") + " · " + c.participants + " " + (L.participants || "participants");
                    row(c.icon, c.label, sub, function () { pick(c.slug, c.label); });
                });
                renderPlatforms(search.value.trim().toLowerCase());
                if (!list.children.length) {
                    list.appendChild(el("li", "fr-modal-empty", L.empty || ""));
                }
            })
            .catch(function () { /* aborted or offline */ });
    }

    function open(postId, community) {
        current = { postId: postId, community: community || "" };
        search.value = "";
        modal.hidden = false;
        document.body.classList.add("fr-modal-open");
        load();
        setTimeout(function () { search.focus(); }, 30);
    }
    function close() {
        modal.hidden = true;
        document.body.classList.remove("fr-modal-open");
    }

    document.addEventListener("click", function (ev) {
        var btn = ev.target.closest(".fr-crosspost-button");
        if (btn) {
            ev.preventDefault();
            ev.stopPropagation();
            open(btn.getAttribute("data-post-id"), btn.getAttribute("data-community"));
            return;
        }
        if (ev.target.closest("[data-fr-crosspost-close]")) { close(); }
    }, true);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !modal.hidden) { close(); } });
    search.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 180); });
})();
