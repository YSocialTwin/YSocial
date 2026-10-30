(function () {
  "use strict";
  var body = document.body;
  var actUrl = body.getAttribute("data-act-url");
  if (!actUrl) return; // observer pages carry no participant data
  var csrf = body.getAttribute("data-csrf") || "";
  var leaveUrl = body.getAttribute("data-leave-url");
  var lostText = body.getAttribute("data-t-lost") || "";
  var toastEl = document.getElementById("dt-toast");
  var toastTimer = null;

  function toast(text) {
    if (!toastEl) return;
    toastEl.textContent = text;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 4000);
  }

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(payload || {})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) { return { status: r.status, data: data }; });
    });
  }

  // one action; resolves to {ok, outcome, error, data}
  function act(type, payload) {
    return post(actUrl, { actions: [{ type: type, payload: payload || {} }] }).then(function (res) {
      var out = (res.data.outcomes || [])[0];
      if (res.status === 200 && out) return { ok: !!out.success, outcome: out, error: out.error, data: res.data };
      return { ok: false, error: res.data.error || String(res.status), data: res.data, status: res.status };
    }).catch(function () { return { ok: false, error: lostText }; });
  }

  // ---------------------------------------------------------------- deck
  var play = document.getElementById("dt-play");
  if (play) {
    var stage = document.getElementById("dt-stage");
    var btnLike = document.getElementById("dt-like"), btnPass = document.getElementById("dt-pass"), btnSuper = document.getElementById("dt-super");
    var empty = document.getElementById("dt-empty"), more = document.getElementById("dt-more"), quota = document.getElementById("dt-quota");
    var t = function (k) { return play.getAttribute("data-t-" + k) || ""; };
    var cards = [], busy = false, limits = { likes: 0, supers: 0 };

    var el = function (tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined && text !== null) n.textContent = text;
      return n;
    };
    var setEnabled = function (on) { [btnLike, btnPass, btnSuper].forEach(function (b) { if (b) b.disabled = !on; }); };
    var showQuota = function () {
      if (quota) quota.textContent = limits.likes + " " + t("likes") + " · " + limits.supers + " " + t("supers");
      if (btnLike) btnLike.disabled = busy || !cards.length || limits.likes <= 0;
      if (btnSuper) btnSuper.disabled = busy || !cards.length || limits.supers <= 0;
    };

    var renderCard = function (c) {
      var a = el("article", "dt-card dt-swipe");
      var photo = el("div", "dt-card-photo");
      photo.style.setProperty("--dt-hue", String(Math.abs(hash(c.candidate_id)) % 360));
      var urls = (c.photo_urls || []).filter(function (u) { return u; });
      var base = play.getAttribute("data-media") || "";
      if (urls.length) {
        var img = el("img", "dt-card-img");
        img.src = base + encodeURI(urls[0]);
        img.alt = (c.photos && c.photos[0]) || "";
        img.loading = "lazy";
        photo.appendChild(img);
      } else {
        photo.appendChild(el("span", "dt-avatar dt-avatar-xl", (c.username || "?").slice(0, 2).toUpperCase()));
      }
      if (c.superliked_you) photo.appendChild(el("span", "dt-stamp dt-stamp-like", t("super-from")));
      a.appendChild(photo);
      var b = el("div", "dt-card-body");
      var h = el("h3", "", c.username || "");
      if (c.age) h.appendChild(el("span", "dt-age", ", " + c.age));
      b.appendChild(h);
      var meta = [];
      if (c.distance_km !== null && c.distance_km !== undefined) meta.push(Math.round(c.distance_km) + " km " + t("away"));
      if (c.intent) meta.push(c.intent);
      b.appendChild(el("p", "dt-meta", meta.join(" · ")));
      if (c.bio) b.appendChild(el("p", "dt-bio", c.bio));
      var answers = c.answers || {};
      Object.keys(answers).forEach(function (q) {
        var d = el("p", "dt-bio");
        d.appendChild(el("strong", "", q + " "));
        d.appendChild(document.createTextNode(answers[q]));
        b.appendChild(d);
      });
      if (c.interests && c.interests.length) {
        var ul = el("ul", "dt-tags");
        c.interests.slice(0, 8).forEach(function (i) { ul.appendChild(el("li", "", i)); });
        b.appendChild(ul);
      }
      if (urls.length > 1) {
        var strip = el("div", "dt-thumbs");
        urls.slice(1, 5).forEach(function (u) {
          var t = el("img");
          t.src = base + encodeURI(u);
          t.alt = "";
          t.loading = "lazy";
          strip.appendChild(t);
        });
        b.appendChild(strip);
      }
      if (c.photos && c.photos.length) b.appendChild(el("p", "dt-photolist", c.photos.join(" · ")));
      a.appendChild(b);
      return a;
    };

    function hash(s) { var h = 0; for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; } return h; }

    var draw = function () {
      stage.textContent = "";
      if (!cards.length) { empty.hidden = false; setEnabled(false); showQuota(); return; }
      empty.hidden = true;
      var node = renderCard(cards[0]);
      stage.appendChild(node);
      attachDrag(node);
      showQuota();
    };

    var load = function () {
      busy = true; setEnabled(false);
      return fetch(play.getAttribute("data-deck-url"), { credentials: "same-origin" }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, data: d }; });
      }).then(function (res) {
        busy = false;
        if (res.status === 403) { toast(t("off")); cards = []; draw(); return; }
        if (res.status !== 200) { toast(t("lost")); cards = []; draw(); return; }
        cards = res.data.cards || [];
        limits.likes = res.data.likes_left || 0;
        limits.supers = res.data.superlikes_left || 0;
        draw();
      }).catch(function () { busy = false; toast(t("lost")); draw(); });
    };

    var decide = function (kind) {
      if (busy || !cards.length) return;
      var card = cards[0];
      if (kind === "LIKE" && limits.likes <= 0) return;
      if (kind === "SUPERLIKE" && limits.supers <= 0) return;
      busy = true; setEnabled(false);
      act(kind, { target_id: card.candidate_id }).then(function (res) {
        busy = false;
        if (!res.ok) { toast(res.error || t("lost")); draw(); return; }
        if (kind === "LIKE") limits.likes -= 1;
        if (kind === "SUPERLIKE") limits.supers -= 1;
        cards.shift();
        if ((res.outcome.new_ids || []).length > 1) {
          toast(t("match") + " " + (card.username || ""));
        }
        draw();
      });
    };

    var attachDrag = function (node) {
      var x0 = null, y0 = null, dx = 0, dy = 0;
      node.addEventListener("pointerdown", function (e) { x0 = e.clientX; y0 = e.clientY; node.setPointerCapture(e.pointerId); });
      node.addEventListener("pointermove", function (e) {
        if (x0 === null) return;
        dx = e.clientX - x0; dy = e.clientY - y0;
        node.style.transform = "translate(" + dx + "px," + Math.min(0, dy) + "px) rotate(" + dx / 20 + "deg)";
      });
      var end = function () {
        if (x0 === null) return;
        var d = dx, v = dy;
        x0 = null; dx = 0; dy = 0;
        node.style.transform = "";
        if (v < -120 && Math.abs(d) < 100) decide("SUPERLIKE");
        else if (d > 100) decide("LIKE");
        else if (d < -100) decide("PASS");
      };
      node.addEventListener("pointerup", end);
      node.addEventListener("pointercancel", function () { x0 = null; node.style.transform = ""; });
    };

    btnLike.addEventListener("click", function () { decide("LIKE"); });
    btnPass.addEventListener("click", function () { decide("PASS"); });
    btnSuper.addEventListener("click", function () { decide("SUPERLIKE"); });
    if (more) more.addEventListener("click", load);
    document.addEventListener("keydown", function (e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName)) return;
      if (e.key === "ArrowRight") decide("LIKE");
      else if (e.key === "ArrowLeft") decide("PASS");
      else if (e.key === "ArrowUp") decide("SUPERLIKE");
    });
    load();
  }

  // ------------------------------------------- generic actions (chat, profile, settings)
  var csv = function (v) { return (v || "").split(",").filter(Boolean); };

  function payloadOf(node) {
    var p = {};
    try { p = JSON.parse(node.getAttribute("data-payload") || "{}"); } catch (e) { p = {}; }
    var from = node.getAttribute("data-from"); // ids of inputs whose value joins the payload (name=id)
    csv(from).forEach(function (id) { var i = document.getElementById(id); if (i) p[i.getAttribute("name") || id] = i.value; });
    return p;
  }

  function finish(res, node) {
    if (res.ok) {
      if (node.getAttribute("data-reload") !== "0") location.reload();
      return;
    }
    toast(res.error || "error");
  }

  document.addEventListener("click", function (e) {
    var node = e.target.closest("[data-act]");
    if (node && !node.form && node.tagName !== "FORM") {
      e.preventDefault();
      var q = node.getAttribute("data-confirm");
      if (q && !window.confirm(q)) return;
      act(node.getAttribute("data-act"), payloadOf(node)).then(function (res) { finish(res, node); });
      return;
    }
    var leave = e.target.closest("[data-leave]");
    if (leave && leaveUrl) {
      var ask = leave.getAttribute("data-confirm");
      if (ask && !window.confirm(ask)) return;
      post(leaveUrl, {}).then(function (res) { if (res.status === 200) location.reload(); else toast(res.data.error || "error"); });
    }
  });

  // upload of a picture: multipart, checked and re-encoded by the server
  document.addEventListener("submit", function (e) {
    var up = e.target.closest("form[data-upload]");
    if (!up) return;
    e.preventDefault();
    var button = up.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    fetch(up.getAttribute("data-upload"), {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrf },
      body: new FormData(up)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, data: d }; });
    }).then(function (res) {
      if (res.status === 200 && res.data.ok) { location.reload(); return; }
      toast(res.data.error || "error");
      if (button) button.disabled = false;
    }).catch(function () {
      toast(up.getAttribute("data-t-lost") || "");
      if (button) button.disabled = false;
    });
  });

  document.addEventListener("submit", function (e) {
    var form = e.target.closest("form[data-act]");
    if (!form) return;
    e.preventDefault();
    var p = payloadOf(form);
    var ints = csv(form.getAttribute("data-int")), floats = csv(form.getAttribute("data-float"));
    new FormData(form).forEach(function (value, key) {
      if (ints.indexOf(key) >= 0) p[key] = parseInt(value, 10);
      else if (floats.indexOf(key) >= 0) p[key] = parseFloat(value);
      else p[key] = value;
    });
    var type = form.getAttribute("data-act");
    if (type === "REPLY" || type === "SEND_MESSAGE") {
      if (!String(p.text || "").trim()) return;
    }
    act(type, p).then(function (res) { finish(res, form); });
  });
})();
