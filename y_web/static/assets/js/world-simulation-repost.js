/* Repost on another platform (World Simulation): a menu of the other platforms where the person is enrolled, opened by
   any [data-ws-repost] button (data-ws-exp, data-post-id, data-text). The server recomputes the destinations. */
(function () {
  "use strict";
  if (window.wsRepostMenu) { return; }
  var menu = null, platforms = null;
  function csrf() {
    var h = { "Content-Type": "application/json" }, m = document.querySelector('meta[name="csrf-token"]');
    if (m) { h["X-CSRFToken"] = m.getAttribute("content"); }
    return h;
  }
  function labels(btn) { try { return JSON.parse(btn.getAttribute("data-i18n") || "{}"); } catch (e) { return {}; } }
  function say(text) {
    var t = document.createElement("div");
    t.textContent = text;
    t.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#222;color:#fff;padding:8px 14px;border-radius:999px;font-size:13px;z-index:10001";
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 4000);
  }
  function close() { if (menu) { menu.remove(); menu = null; } }
  function load(exp) {
    if (platforms) { return Promise.resolve(platforms); }
    return fetch("/" + exp + "/federation/repost_targets", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { platforms: [] }; })
      .then(function (d) { platforms = d.platforms || []; return platforms; })
      .catch(function () { return []; });
  }
  function send(btn, p) {
    var L = labels(btn);
    close();
    fetch("/" + btn.getAttribute("data-ws-exp") + "/federation/repost", {
      method: "POST", credentials: "same-origin", headers: csrf(),
      body: JSON.stringify({ members: [p.member], post_id: btn.getAttribute("data-post-id") || null, text: btn.getAttribute("data-text") || "" })
    }).then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function () { say((L.posted || "Reposted to") + " " + p.label); })
      .catch(function () { say(L.error || "Unable to repost right now."); });
  }
  function open(btn) {
    close();
    load(btn.getAttribute("data-ws-exp")).then(function (list) {
      if (!list.length) { return; }
      var L = labels(btn), box = btn.getBoundingClientRect();
      menu = document.createElement("div");
      menu.setAttribute("role", "menu");
      menu.style.cssText = "position:fixed;z-index:10000;min-width:220px;background:#fff;color:#0f1a1c;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.18);padding:6px 0;left:" + Math.max(8, Math.min(box.left, window.innerWidth - 240)) + "px;top:" + Math.min(box.bottom + 4, window.innerHeight - 40 - list.length * 38) + "px";
      var h = document.createElement("div");
      h.textContent = L.title || "Other platforms";
      h.style.cssText = "padding:6px 14px;font-size:12px;font-weight:700;color:#576f76;text-transform:uppercase";
      menu.appendChild(h);
      list.forEach(function (p) {
        var b = document.createElement("button");
        b.type = "button"; b.setAttribute("role", "menuitem"); b.textContent = p.label;
        b.style.cssText = "display:block;width:100%;text-align:left;background:none;border:0;padding:8px 14px;font-size:14px;cursor:pointer;color:inherit";
        b.onmouseenter = function () { b.style.background = "#eaedef"; };
        b.onmouseleave = function () { b.style.background = "none"; };
        b.addEventListener("click", function () { send(btn, p); });
        menu.appendChild(b);
      });
      document.body.appendChild(menu);
    });
  }
  window.wsRepostMenu = open;
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("[data-ws-repost]");
    if (btn) { ev.preventDefault(); ev.stopPropagation(); open(btn); return; }
    if (menu && !menu.contains(ev.target)) { close(); }
  }, true);
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { close(); } });
})();
