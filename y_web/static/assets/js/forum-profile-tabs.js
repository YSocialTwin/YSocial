/* Profile tabs without a full page reload: fetch the target tab, swap the posts list, keep URL and history in sync. */
(function () {
    "use strict";
    var TAB_SELECTOR = ".forum-profile-tab";
    var inflight = null;

    function parseUrl(url) {
        var m = new URL(url, window.location.origin).pathname.match(/\/profile\/([^/]+)\/([^/]+)\/(\d+)/);
        return m ? { userId: m[1], mode: m[2], page: parseInt(m[3], 10) || 1 } : null;
    }

    function setActiveTab(mode) {
        document.querySelectorAll(TAB_SELECTOR).forEach(function (tab) {
            var info = parseUrl(tab.getAttribute("href") || "");
            tab.classList.toggle("is-active", !!info && info.mode === mode);
        });
    }

    function load(url, push) {
        var info = parseUrl(url);
        var container = document.getElementById("posts-container");
        if (!info || !container) {
            window.location.href = url;
            return;
        }
        if (inflight) { inflight.abort(); }
        var ctrl = new AbortController();
        inflight = ctrl;
        container.classList.add("is-loading");
        fetch(url, { credentials: "same-origin", signal: ctrl.signal, headers: { "X-Requested-With": "fetch" } })
            .then(function (r) {
                if (!r.ok) { throw new Error("HTTP " + r.status); }
                return r.text();
            })
            .then(function (html) {
                var doc = new DOMParser().parseFromString(html, "text/html");
                var fresh = doc.getElementById("posts-container");
                if (!fresh) { throw new Error("missing-container"); }
                if (window.InfiniteScroll) { window.InfiniteScroll.destroy(); }
                container.innerHTML = fresh.innerHTML;
                container.classList.remove("is-loading");
                setActiveTab(info.mode);
                if (push) { window.history.pushState({ frProfileTab: true }, "", url); }
                var cfg = window.YS_DATA_FORUM_PROFILE = window.YS_DATA_FORUM_PROFILE || {};
                cfg.mode = info.mode;
                cfg.page = info.page;
                if (window.redditProfileHydrate) { window.redditProfileHydrate(); }
                if (window.InfiniteScroll) {
                    window.InfiniteScroll.init({
                        apiEndpoint: "/" + (cfg.expId || "") + "/api/profile/" + (cfg.userId || info.userId) + "/" + info.mode,
                        postsContainerId: "posts-container",
                        initialPage: info.page
                    });
                }
            })
            .catch(function (err) {
                if (err && err.name === "AbortError") { return; }
                window.location.href = url; // fall back to a normal navigation
            });
    }

    document.addEventListener("click", function (ev) {
        var tab = ev.target.closest(TAB_SELECTOR);
        if (!tab || ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) { return; }
        var href = tab.getAttribute("href");
        if (!href || tab.classList.contains("is-active")) { ev.preventDefault(); return; }
        ev.preventDefault();
        load(href, true);
    });

    window.addEventListener("popstate", function () {
        if (parseUrl(window.location.href)) { load(window.location.href, false); }
    });
})();
