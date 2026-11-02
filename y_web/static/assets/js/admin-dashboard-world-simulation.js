/* World Simulation box of the admin home page: live cards.
   One request per tick of the timer for all the cards (the server answers with the rendered cards); 5 s while a World Simulation
   is in progress, 30 s otherwise; nothing is requested while the tab is hidden and never two requests at once. */
(function () {
    'use strict';
    var box = document.getElementById('box-world-simulations');
    var holder = document.getElementById('world-simulation-cards');
    if (!box || !holder || !box.dataset.pollUrl) { return; }
    var url = box.dataset.pollUrl;
    var activeMs = parseInt(box.dataset.pollActiveMs, 10) || 5000;
    var idleMs = parseInt(box.dataset.pollIdleMs, 10) || 30000;
    var timer = null;
    var busy = false;
    var stopped = false;

    // confirmation of the destructive buttons (the text is in data-confirm, so it needs no escaping)
    box.addEventListener('submit', function (event) {
        var message = event.target && event.target.getAttribute && event.target.getAttribute('data-confirm');
        if (message && !window.confirm(message)) { event.preventDefault(); }
    });

    function anyActive() { return !!holder.querySelector('[data-state="starting"],[data-state="running"],[data-state="paused"],[data-state="stopping"]'); }

    function apply(answer) {
        if (!answer || answer.available === false) { stopped = true; return; }
        var cards = answer.cards || [];
        var byId = {};
        Array.prototype.forEach.call(holder.children, function (el) { byId[el.getAttribute('data-fed-id')] = el; });
        var previous = null;
        cards.forEach(function (card) {
            var key = String(card.id);
            var tpl = document.createElement('template');
            tpl.innerHTML = card.html.trim();
            var fresh = tpl.content.firstElementChild;
            var current = byId[key];
            if (current) {
                if (current.outerHTML !== fresh.outerHTML) { holder.replaceChild(fresh, current); current = fresh; }
                delete byId[key];
            } else {
                holder.insertBefore(fresh, previous ? previous.nextSibling : holder.firstChild);
                current = fresh;
            }
            previous = current;
        });
        Object.keys(byId).forEach(function (key) { holder.removeChild(byId[key]); });
        var section = document.getElementById('section-world-simulation');
        if (section) { section.hidden = !cards.length; }
    }

    function schedule() {
        if (timer) { window.clearTimeout(timer); timer = null; }
        if (stopped || document.hidden) { return; }
        timer = window.setTimeout(poll, anyActive() ? activeMs : idleMs);
    }

    function poll() {
        timer = null;
        if (busy || document.hidden) { schedule(); return; }
        busy = true;
        fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (answer) { if (answer) { apply(answer); } })
            .catch(function () { /* the next tick tries again */ })
            .then(function () { busy = false; schedule(); });
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) { if (timer) { window.clearTimeout(timer); timer = null; } } else if (!busy) { poll(); }
    });
    schedule();
})();
