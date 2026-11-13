/* Create a community (subreddit) as the human user, then open it. */
(function () {
    "use strict";
    var modal = document.getElementById("fr-create-community");
    if (!modal) { return; }
    var expId = modal.getAttribute("data-exp-id");
    var form = document.getElementById("fr-create-community-form");
    var input = document.getElementById("fr-create-community-name");
    var err = document.getElementById("fr-create-community-error");
    var L = {};
    try { L = JSON.parse(modal.getAttribute("data-i18n") || "{}"); } catch (e) { L = {}; }
    var NAME = /^[a-z0-9_]{3,20}$/;

    function open() {
        input.value = ""; err.hidden = true;
        modal.hidden = false;
        document.body.classList.add("fr-modal-open");
        setTimeout(function () { input.focus(); }, 30);
    }
    function close() { modal.hidden = true; document.body.classList.remove("fr-modal-open"); }
    function fail(text) { err.textContent = text; err.hidden = false; }

    document.addEventListener("click", function (ev) {
        if (ev.target.closest("[data-fr-create-community]")) { ev.preventDefault(); open(); return; }
        if (ev.target.closest("[data-fr-create-close]")) { close(); }
    });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !modal.hidden) { close(); } });
    form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var name = input.value.trim().toLowerCase().replace(/^y\//, "");
        if (!NAME.test(name)) { fail(L.invalid || "Invalid name"); return; }
        var headers = { "Content-Type": "application/json" };
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) { headers["X-CSRFToken"] = meta.getAttribute("content"); }
        fetch("/api/reddit/" + expId + "/communities", { method: "POST", credentials: "same-origin", headers: headers, body: JSON.stringify({ name: name }) })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
            .then(function (res) {
                if (!res.ok) { fail(res.body.error || L.error || "Error"); return; }
                window.location.href = (res.body.data || res.body).url;
            })
            .catch(function () { fail(L.error || "Error"); });
    });
})();
