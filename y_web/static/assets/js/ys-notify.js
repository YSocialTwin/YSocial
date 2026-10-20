/* Admin notifications (YNotify)
 *
 * One way to tell the user about errors, successes and information in the admin
 * panel, including the pages added by plugins:
 *   YNotify.error(msg[, opts])   red     stays until closed
 *   YNotify.success(msg[, opts]) green   closes by itself
 *   YNotify.info(msg[, opts])    yellow  closes by itself (YNotify.warning is the same)
 *   YNotify.show(kind, msg[, opts])
 * opts: { title, details: [string], timeout: ms (0 = until closed) }
 * msg may also be an Error or the structured object used by the server
 * ({title, summary, failures: [{source, target, reason}]}).
 *
 * Cards are fixed in the top-right corner, stacked one under the other, and never
 * move the page. Server-side flash() messages are rendered by
 * admin/_flash_messages.html as JSON and shown here; window.alert and the legacy
 * window.showToast are routed through the same cards.
 */
(function () {
    'use strict';
    if (window.YNotify) return;

    var MAX_VISIBLE = 6;
    var TIMEOUT = { success: 5000, info: 8000, error: 0 };
    var KIND = {
        error: 'error', err: 'error', danger: 'error', fail: 'error', failure: 'error',
        success: 'success', ok: 'success',
        info: 'info', warning: 'info', warn: 'info', notice: 'info', message: 'info'
    };
    var GLYPH = { error: '✕', success: '✓', info: '!' };
    var reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    var nativeAlert = window.alert ? window.alert.bind(window) : function () {};
    var pending = [];

    function tr(text) {
        try { if (window.YI18n && typeof window.YI18n.t === 'function') return window.YI18n.t(text); } catch (e) { /* ignore */ }
        return text;
    }

    function container() {
        var c = document.getElementById('ys-notify');
        if (c) return c;
        if (!document.body) return null;
        c = document.createElement('div');
        c.id = 'ys-notify';
        c.className = 'ys-notify';
        c.setAttribute('role', 'region');
        c.setAttribute('aria-live', 'polite');
        c.setAttribute('aria-label', tr('Notice'));
        document.body.appendChild(c);
        return c;
    }

    function normalize(msg, opts) {
        var out = { title: opts.title || '', text: '', details: opts.details || [] };
        if (msg && typeof msg === 'object') {
            if (msg instanceof Error) {
                out.text = msg.message || String(msg);
            } else {
                out.title = out.title || msg.title || '';
                out.text = msg.summary || msg.message || '';
                if (msg.failures && msg.failures.length) {
                    out.details = out.details.concat(msg.failures.map(function (f) {
                        return (f.source || '') + (f.target ? ' - target ' + f.target : '') + ': ' + (f.reason || '');
                    }));
                }
            }
        } else if (msg != null) {
            out.text = String(msg);
        }
        // the card already has an icon: drop the decorative marks some messages start with
        out.text = out.text.replace(/^\s*[\u2713\u2717\u2715\u25CF]\s*/, '');
        return out;
    }

    function dismiss(el) {
        if (!el || !el.parentNode || el._leaving) return;
        el._leaving = true;
        clearTimeout(el._timer);
        if (reduced) { el.parentNode.removeChild(el); return; }
        el.classList.add('is-leaving');
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    }

    function arm(el, ms) {
        clearTimeout(el._timer);
        if (ms > 0) el._timer = setTimeout(function () { dismiss(el); }, ms);
    }

    function build(kind, n, timeout) {
        var el = document.createElement('div');
        el.className = 'ys-toast is-' + kind;
        el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
        var ic = document.createElement('span');
        ic.className = 'ys-toast-ic';
        ic.setAttribute('aria-hidden', 'true');
        ic.textContent = GLYPH[kind];
        var body = document.createElement('div');
        body.className = 'ys-toast-body';
        if (n.title) {
            var t = document.createElement('strong');
            t.className = 'ys-toast-title';
            t.textContent = n.title;
            body.appendChild(t);
        }
        if (n.text) {
            var p = document.createElement('span');
            p.className = 'ys-toast-text';
            p.textContent = n.text;
            body.appendChild(p);
        }
        if (n.details.length) {
            var ul = document.createElement('ul');
            ul.className = 'ys-toast-details';
            n.details.forEach(function (d) {
                var li = document.createElement('li');
                li.textContent = d;
                ul.appendChild(li);
            });
            body.appendChild(ul);
        }
        var x = document.createElement('button');
        x.type = 'button';
        x.className = 'ys-toast-x';
        x.setAttribute('aria-label', tr('Close'));
        x.innerHTML = '&times;';
        x.addEventListener('click', function () { dismiss(el); });
        el.appendChild(ic);
        el.appendChild(body);
        el.appendChild(x);
        el.addEventListener('mouseenter', function () { clearTimeout(el._timer); });
        el.addEventListener('mouseleave', function () { arm(el, timeout > 0 ? Math.min(timeout, 2500) : 0); });
        return el;
    }

    function show(kind, msg, opts) {
        if (typeof opts === 'number') opts = { timeout: opts };
        opts = opts || {};
        kind = KIND[String(kind || 'info').toLowerCase()] || 'info';
        var n = normalize(msg, opts);
        if (!n.title && !n.text && !n.details.length) return null;
        var c = container();
        if (!c) { pending.push([kind, msg, opts]); return null; }
        var timeout = opts.timeout != null ? opts.timeout : TIMEOUT[kind];
        var key = kind + '\u0001' + n.title + '\u0001' + n.text + '\u0001' + n.details.join('|');
        var same = c.querySelectorAll('.ys-toast');
        for (var i = 0; i < same.length; i++) {
            if (same[i]._key === key && !same[i]._leaving) {
                same[i].classList.remove('is-pulse');
                void same[i].offsetWidth;
                same[i].classList.add('is-pulse');
                arm(same[i], timeout);
                return same[i];
            }
        }
        var el = build(kind, n, timeout);
        el._key = key;
        c.appendChild(el);
        arm(el, timeout);
        var live = c.querySelectorAll('.ys-toast:not(.is-leaving)');
        for (var j = 0; live.length - j > MAX_VISIBLE; j++) dismiss(live[j]);
        return el;
    }

    function classify(text) {
        var s = String(text == null ? '' : text);
        if (/(^|\W)(error|errors|fail|failed|failure|unable|could not|couldn't|cannot|can't|invalid|denied|offline|not available|not found|unexpected)(\W|$)/i.test(s)) return 'error';
        if (/(^|\W)(success|successfully|saved|completed|updated|created|deleted|done)(\W|$)/i.test(s)) return 'success';
        return 'info';
    }

    function flush() {
        var data = document.getElementById('ys-flash-data');
        if (data && !data._read) {
            data._read = true;
            try {
                JSON.parse(data.textContent || '[]').forEach(function (m) { show(m.category, m.message); });
            } catch (e) { /* malformed flash payload: ignore */ }
        }
        // Server-rendered notices can opt in with data-ys-notify="error|success|info|warning":
        // the element stays hidden (see ys-notify.css) and its text is shown as a card instead.
        [].slice.call(document.querySelectorAll('[data-ys-notify]')).forEach(function (e) {
            if (e._ysDone) return;
            e._ysDone = true;
            show(e.getAttribute('data-ys-notify'), (e.textContent || '').replace(/\s+/g, ' ').trim());
        });
        pending.splice(0).forEach(function (a) { show(a[0], a[1], a[2]); });
    }

    window.YNotify = {
        show: show,
        error: function (m, o) { return show('error', m, o); },
        success: function (m, o) { return show('success', m, o); },
        info: function (m, o) { return show('info', m, o); },
        warning: function (m, o) { return show('info', m, o); },
        dismiss: dismiss,
        clear: function () { var c = document.getElementById('ys-notify'); if (c) [].slice.call(c.children).forEach(dismiss); },
        classify: classify,
        nativeAlert: nativeAlert
    };

    /* Legacy entry points keep working, now as cards instead of blocking boxes or overlapping toasts. */
    window.alert = function (message) { show(classify(message), message); };
    window.showToast = function (message, type, duration) {
        return show(type || 'info', message, duration != null ? { timeout: duration } : {});
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', flush);
    else flush();
})();
