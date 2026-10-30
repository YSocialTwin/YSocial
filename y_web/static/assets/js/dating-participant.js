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
    var matchBox = document.getElementById("dt-match");
    var t = function (k) { return play.getAttribute("data-t-" + k) || ""; };
    var base = play.getAttribute("data-media") || "";
    var cards = [], nodes = [], busy = false, limits = { likes: 0, supers: 0 };
    var THRESHOLD = 110, SUPER_THRESHOLD = 120, VISIBLE = 3;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var el = function (tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined && text !== null) n.textContent = text;
      return n;
    };
    function hash(s) { var h = 0; for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; } return h; }
    var setEnabled = function (on) { [btnLike, btnPass, btnSuper].forEach(function (b) { if (b) b.disabled = !on; }); };
    var showQuota = function () {
      if (quota) {
        quota.textContent = "";
        quota.appendChild(el("span", "dt-pill dt-pill-like", "♥ " + limits.likes + " " + t("likes")));
        quota.appendChild(el("span", "dt-pill dt-pill-super", "★ " + limits.supers + " " + t("supers")));
      }
      btnPass.disabled = busy || !cards.length;
      btnLike.disabled = busy || !cards.length || limits.likes <= 0;
      btnSuper.disabled = busy || !cards.length || limits.supers <= 0;
    };

    var withClass = function (tag, first, second, text) {
      var n = el(tag, first, text);
      n.classList.add(second);
      return n;
    };
    var stampOf = function (kind, text) { return withClass("span", "dt-c-stamp", "dt-c-stamp-" + kind, text); };
    var chipOf = function (kind, text) { return withClass("span", "dt-chip", "dt-chip-" + kind, text); };

    var renderCard = function (c) {
      var a = el("article", "dt-card2");
      a.setAttribute("data-id", c.candidate_id);
      var photo = el("div", "dt-c-photo");
      photo.style.setProperty("--dt-hue", String(Math.abs(hash(c.candidate_id)) % 360));
      var urls = (c.photo_urls || []).filter(function (u) { return u; });
      var imgs = urls.map(function (u, i) {
        var img = el("img", "dt-c-img" + (i === 0 ? " is-on" : ""));
        img.src = base + encodeURI(u);
        img.alt = "";
        img.draggable = false;
        if (i > 0) img.loading = "lazy";
        photo.appendChild(img);
        return img;
      });
      if (!imgs.length) photo.appendChild(el("span", "dt-avatar dt-avatar-xl", (c.username || "?").slice(0, 2).toUpperCase()));
      if (imgs.length > 1) {
        var dots = el("div", "dt-c-dots");
        imgs.forEach(function (_, i) { dots.appendChild(el("i", i === 0 ? "is-on" : "")); });
        photo.appendChild(dots);
        var at = 0;
        photo.addEventListener("click", function (e) {
          if (a.__moved) return;
          var r = photo.getBoundingClientRect();
          at = (at + (e.clientX - r.left < r.width / 2 ? imgs.length - 1 : 1)) % imgs.length;
          imgs.forEach(function (im, i) { im.classList.toggle("is-on", i === at); });
          Array.prototype.forEach.call(dots.children, function (d, i) { d.classList.toggle("is-on", i === at); });
        });
      }
      a.appendChild(photo);
      a.appendChild(stampOf("like", t("like")));
      a.appendChild(stampOf("nope", t("nope")));
      a.appendChild(stampOf("super", t("super")));

      var info = el("div", "dt-c-info");
      var chips = el("div", "dt-c-chips");
      if (c.superliked_you) chips.appendChild(chipOf("super", "★ " + t("super-from")));
      if (c.previous) chips.appendChild(el("span", "dt-chip", "↺ " + t("seen")));
      if (chips.childNodes.length) info.appendChild(chips);
      var h = el("h3", "", c.username || "");
      if (c.age) h.appendChild(el("span", "dt-c-age", " " + c.age));
      info.appendChild(h);
      var meta = [];
      if (c.distance_km !== null && c.distance_km !== undefined) meta.push(Math.round(c.distance_km) + " km " + t("away"));
      if (c.intent) meta.push(c.intent.charAt(0).toUpperCase() + c.intent.slice(1));
      if (meta.length) info.appendChild(el("p", "dt-c-meta", meta.join(" · ")));
      var detail = el("div", "dt-c-detail");
      if (c.bio) detail.appendChild(el("p", "dt-c-bio", c.bio));
      var answers = c.answers || {};
      Object.keys(answers).forEach(function (q) {
        var d = el("p", "dt-c-ans");
        d.appendChild(el("strong", "", q + " "));
        d.appendChild(document.createTextNode(answers[q]));
        detail.appendChild(d);
      });
      if (c.interests && c.interests.length) {
        var ul = el("ul", "dt-c-tags");
        c.interests.slice(0, 8).forEach(function (i) { ul.appendChild(el("li", "", i)); });
        detail.appendChild(ul);
      }
      info.appendChild(detail);
      if (c.bio || Object.keys(answers).length || (c.interests && c.interests.length)) {
        var toggle = el("button", "dt-c-more", t("more"));
        toggle.type = "button";
        toggle.addEventListener("click", function (e) {
          e.stopPropagation();
          var open = a.classList.toggle("is-open");
          toggle.textContent = open ? t("less") : t("more");
        });
        info.appendChild(toggle);
      }
      a.appendChild(info);
      return a;
    };

    // the first card is on top and draggable, the next ones peek out from underneath
    var layout = function () {
      nodes.forEach(function (n, i) {
        n.classList.toggle("is-top", i === 0);
        n.style.zIndex = String(10 - i);
        n.style.opacity = i < VISIBLE ? "1" : "0";
        n.style.transform = i === 0 ? "" : "translateY(" + 12 * i + "px) scale(" + (1 - 0.045 * i) + ")";
      });
    };

    var fill = function () {
      while (nodes.length < Math.min(VISIBLE, cards.length)) {
        var n = renderCard(cards[nodes.length]);
        n.style.opacity = "0";
        stage.appendChild(n);
        nodes.push(n);
      }
      layout();
      if (nodes[0]) attachDrag(nodes[0]);
    };

    var draw = function () {
      stage.textContent = "";
      nodes = [];
      if (!cards.length) { empty.hidden = false; showQuota(); return; }
      empty.hidden = true;
      fill();
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

    var stamps = function (node, dx, dy) {
      var like = node.querySelector(".dt-c-stamp-like"), nope = node.querySelector(".dt-c-stamp-nope"), sup = node.querySelector(".dt-c-stamp-super");
      var up = dy < 0 ? Math.min(1, -dy / SUPER_THRESHOLD) : 0;
      var side = Math.min(1, Math.abs(dx) / THRESHOLD);
      like.style.opacity = dx > 0 && up < 0.8 ? String(side) : "0";
      nope.style.opacity = dx < 0 && up < 0.8 ? String(side) : "0";
      sup.style.opacity = String(up > side ? up : 0);
      node.style.setProperty("--dt-glow", dx > 0 ? "rgba(34,197,94," + side * 0.55 + ")" : dx < 0 ? "rgba(239,68,68," + side * 0.55 + ")" : "transparent");
    };

    var fly = function (node, kind) {
      var w = Math.max(window.innerWidth, 600);
      node.classList.add("is-flying");
      node.style.transition = reduce ? "opacity .01s" : "transform .38s cubic-bezier(.3,.7,.4,1), opacity .38s ease";
      if (kind === "SUPERLIKE") node.style.transform = "translate(0, -" + window.innerHeight + "px) scale(.9)";
      else node.style.transform = "translate(" + (kind === "LIKE" ? w : -w) + "px, -40px) rotate(" + (kind === "LIKE" ? 28 : -28) + "deg)";
      node.style.opacity = "0";
      var stampOf = { LIKE: ".dt-c-stamp-like", PASS: ".dt-c-stamp-nope", SUPERLIKE: ".dt-c-stamp-super" }[kind];
      var s = node.querySelector(stampOf);
      if (s) s.style.opacity = "1";
    };

    var showMatch = function (name) {
      if (!matchBox) { toast(t("match") + " " + name); return; }
      matchBox.textContent = "";
      var box = el("div", "dt-match-box");
      box.appendChild(el("div", "dt-match-hearts", "♥ ♥ ♥"));
      box.appendChild(el("h3", "", t("match")));
      box.appendChild(el("p", "", name));
      var row = el("div", "dt-match-row");
      var open = el("a", "dt-btn", t("open"));
      open.href = play.getAttribute("data-matches-url") || "#";
      var keep = el("button", "dt-btn dt-btn-ghost", t("keep"));
      keep.type = "button";
      keep.addEventListener("click", function () { matchBox.hidden = true; });
      row.appendChild(open); row.appendChild(keep);
      box.appendChild(row);
      matchBox.appendChild(box);
      matchBox.hidden = false;
      keep.focus();
    };

    var decide = function (kind) {
      if (busy || !cards.length) return;
      var card = cards[0], node = nodes[0];
      if (kind === "LIKE" && limits.likes <= 0) return;
      if (kind === "SUPERLIKE" && limits.supers <= 0) return;
      busy = true; setEnabled(false);
      fly(node, kind);
      act(kind, { target_id: card.candidate_id }).then(function (res) {
        busy = false;
        if (!res.ok) {  // the card comes back
          node.classList.remove("is-flying");
          node.style.transition = "";
          node.style.opacity = "1";
          layout();
          stamps(node, 0, 0);
          toast(res.error || t("lost"));
          showQuota();
          return;
        }
        if (kind === "LIKE") limits.likes -= 1;
        if (kind === "SUPERLIKE") limits.supers -= 1;
        cards.shift(); nodes.shift();
        setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 400);
        if (!cards.length) { setTimeout(function () { if (!cards.length) { empty.hidden = false; } }, reduce ? 0 : 300); }
        fill();
        showQuota();
        if ((res.outcome.new_ids || []).length > 1) showMatch(card.username || "");
      });
    };

    var attachDrag = function (node) {
      if (node.__drag) return;
      node.__drag = true;
      var x0 = null, y0 = null, dx = 0, dy = 0;
      node.addEventListener("pointerdown", function (e) {
        if (busy || e.target.closest("button")) return;
        x0 = e.clientX; y0 = e.clientY; dx = 0; dy = 0; node.__moved = false;
        node.style.transition = "none";
        node.setPointerCapture(e.pointerId);
      });
      node.addEventListener("pointermove", function (e) {
        if (x0 === null) return;
        dx = e.clientX - x0; dy = e.clientY - y0;
        if (Math.abs(dx) + Math.abs(dy) > 6) node.__moved = true;
        node.style.transform = "translate(" + dx + "px," + Math.min(0, dy) * 0.9 + "px) rotate(" + dx / 18 + "deg)";
        stamps(node, dx, Math.min(0, dy));
      });
      var end = function (cancel) {
        if (x0 === null) return;
        var d = dx, v = dy;
        x0 = null; dx = 0; dy = 0;
        node.style.transition = reduce ? "none" : "transform .28s cubic-bezier(.3,1.4,.5,1)";
        setTimeout(function () { node.__moved = false; }, 0);
        if (!cancel && v < -SUPER_THRESHOLD && Math.abs(d) < THRESHOLD && limits.supers > 0) return decide("SUPERLIKE");
        if (!cancel && d > THRESHOLD && limits.likes > 0) return decide("LIKE");
        if (!cancel && d < -THRESHOLD) return decide("PASS");
        node.style.transform = ""; // not far enough: the card springs back
        stamps(node, 0, 0);
      };
      node.addEventListener("pointerup", function () { end(false); });
      node.addEventListener("pointercancel", function () { end(true); });
    };

    btnLike.addEventListener("click", function () { decide("LIKE"); });
    btnPass.addEventListener("click", function () { decide("PASS"); });
    btnSuper.addEventListener("click", function () { decide("SUPERLIKE"); });
    if (more) more.addEventListener("click", load);
    document.addEventListener("keydown", function (e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName)) return;
      if (matchBox && !matchBox.hidden) { if (e.key === "Escape") matchBox.hidden = true; return; }
      if (e.key === "ArrowRight") decide("LIKE");
      else if (e.key === "ArrowLeft") decide("PASS");
      else if (e.key === "ArrowUp") { e.preventDefault(); decide("SUPERLIKE"); }
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
  // opening a chat marks the other person's messages as read (the notifications badge counts the rest)
  var opened = document.getElementById("dt-chat-log");
  if (opened && opened.getAttribute("data-open-match")) {
    act("OPEN_CONVERSATION", { match_id: opened.getAttribute("data-open-match") });
  }
})();
