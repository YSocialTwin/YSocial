/* World Simulation pages: tabs, live status, analytics charts and the behaviour of the parameter form.
   No visible text is written here: texts come from the templates (data-text-* attributes). */
(function () {
    'use strict';

    function $(selector, root) { return (root || document).querySelector(selector); }
    function $all(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
    function text(v) { return v === null || v === undefined ? '-' : String(v); }

    /* ---------------------------------------------------------------- tabs (detail page) */
    function initTabs() {
        var tabs = $all('[data-ws-tab]');
        if (!tabs.length) { return; }
        function show(name) {
            $all('[data-ws-pane]').forEach(function (p) { p.hidden = p.dataset.wsPane !== name; });
            tabs.forEach(function (t) { t.classList.toggle('is-active', t.dataset.wsTab === name); });
            try { history.replaceState(null, '', '#' + name); } catch (e) { /* the address bar is optional */ }
        }
        tabs.forEach(function (t) { t.addEventListener('click', function () { show(t.dataset.wsTab); }); });
        var start = (location.hash || '').replace('#', '');
        if (['configuration', 'execution', 'analytics'].indexOf(start) >= 0 && $('[data-ws-pane="' + start + '"]')) { show(start); }
    }

    /* ---------------------------------------------------------------- live status */
    function initStatus() {
        var box = document.getElementById('world-simulation-detail');
        if (!box || !box.dataset.statusUrl) { return; }
        var url = box.dataset.statusUrl;
        function cell(tr, v) { var td = document.createElement('td'); td.textContent = text(v); tr.appendChild(td); return td; }
        function showProblems(s) {
            var banner = document.getElementById('ws-problems');
            var list = document.getElementById('ws-problems-list');
            var line = document.getElementById('ws-progress-line');
            var down = document.getElementById('ws-coordinator-down');
            if (down) { down.hidden = !(s.state === 'running' && s.coordinator_up === false); }
            if (line) { line.textContent = s.progress_text || ''; line.hidden = !s.progress_text; }
            if (!banner || !list) { return; }
            list.innerHTML = '';
            (s.problems || []).forEach(function (p) {
                var li = document.createElement('li');
                var b = document.createElement('b'); b.textContent = p.label;
                li.appendChild(b);
                li.appendChild(document.createTextNode(' ' + p.text + (p.cause ? '. ' + p.cause : '')));
                if (p.log) {
                    var code = document.createElement('code'); code.textContent = p.log;
                    li.appendChild(document.createTextNode(' ')); li.appendChild(code);
                }
                list.appendChild(li);
            });
            var hint = document.getElementById('ws-problems-hint');
            if (hint) { hint.textContent = s.log_hint || ''; }
            banner.hidden = !(s.problems && s.problems.length);
        }
        function refresh() {
            fetch(url, {credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(function (s) {
                document.getElementById('ws-tick').textContent = text(s.global_tick);
                var tick = s.global_tick;
                document.getElementById('ws-dayslot').textContent = (tick === null || tick === undefined || tick < 0) ? '-' : Math.floor(tick / 24) + ' / ' + (tick % 24);
                document.getElementById('ws-skew').textContent = text(s.skew);
                document.getElementById('ws-messages').textContent = s.bus.messages;
                document.getElementById('ws-deliveries').textContent = s.bus.deliveries;
                var body = $('#ws-members tbody');
                body.innerHTML = '';
                var top = 1;
                s.members.forEach(function (m) { if (m.tick !== null && m.tick !== undefined && m.tick > top) { top = m.tick; } });
                s.members.forEach(function (m) {
                    var tr = document.createElement('tr');
                    cell(tr, m.label); cell(tr, m.experiment);
                    var state = cell(tr, '');
                    var healthCell = null;
                    if (m.state) {
                        var tag = document.createElement('span');
                        tag.className = ['exp-tag', 'ws-state-' + m.state].join(' ');
                        tag.textContent = m.state.charAt(0).toUpperCase() + m.state.slice(1);
                        state.appendChild(tag);
                    } else { state.textContent = '-'; }
                    healthCell = cell(tr, '');
                    if (m.health) {
                        var hb = document.createElement('span');
                        hb.className = 'exp-tag ws-health ws-health-' + m.health.code + (m.health.problem ? ' is-problem' : '');
                        hb.textContent = m.health.text;
                        healthCell.appendChild(hb);
                    }
                    var tickCell = cell(tr, '');
                    tickCell.textContent = text(m.tick) + ' ';
                    if (m.tick !== null && m.tick !== undefined) {
                        var bar = document.createElement('progress');
                        bar.className = 'progress is-info is-small ws-progress';
                        bar.max = top; bar.value = Math.max(0, m.tick);
                        tickCell.appendChild(bar);
                    }
                    cell(tr, (m.waiting_for || []).join(', '));
                    body.appendChild(tr);
                });
                showProblems(s);
                var empty = document.getElementById('ws-members-empty');
                if (empty) { empty.hidden = s.members.length > 0 && s.members.some(function (m) { return m.state; }); }
                var stateTag = document.getElementById('ws-state');
                if (stateTag && s.state) { stateTag.className = ['exp-tag', 'ws-state-' + s.state].join(' '); }
                document.getElementById('ws-events').textContent = s.bus.events.map(function (e) { return e.tick + '  ' + e.kind + '  ' + e.detail; }).join('\n');
                document.getElementById('ws-log').textContent = s.log.join('\n');
            }).catch(function () { /* the next poll retries */ });
        }
        refresh();
        setInterval(refresh, 3000);
    }

    /* ---------------------------------------------------------------- analytics */
    function initAnalytics() {
        var box = document.getElementById('ws-analytics');
        if (!box || typeof Chart === 'undefined') { return; }
        var COLORS = ['#039be5', '#e53935', '#43a047', '#fb8c00', '#8e24aa'];
        var charts = {}, loaded = false;
        function uniq(rows, key) { var seen = {}; rows.forEach(function (r) { seen[r[key]] = 1; }); return Object.keys(seen).sort(); }
        function draw(id, type, labels, datasets, extra) {
            if (charts[id]) { charts[id].destroy(); }
            charts[id] = new Chart(document.getElementById(id), {type: type, data: {labels: labels, datasets: datasets},
                options: Object.assign({responsive: true, maintainAspectRatio: false}, extra || {})});
        }
        function perMember(rows, key, days, members) {
            return members.map(function (m, i) {
                return {label: m, backgroundColor: COLORS[i % COLORS.length], borderColor: COLORS[i % COLORS.length], fill: false,
                        data: days.map(function (d) { var r = rows.filter(function (x) { return x.day === d && x.member === m; })[0]; return r ? r[key] : 0; })};
            });
        }
        function fill(selector, rows, keys, limit) {
            var b = $(selector + ' tbody');
            b.textContent = '';
            rows.slice(0, limit).forEach(function (r) {
                var tr = document.createElement('tr');
                keys.forEach(function (k) { var td = document.createElement('td'); td.textContent = r[k]; tr.appendChild(td); });
                b.appendChild(tr);
            });
        }
        function render(data) {
            var t = data.tables || {};
            document.getElementById('ws-an-state').textContent = (data.state && data.state.state) ? '(' + data.state.state + ')' : '';
            var att = t.daily_attention || [], sur = t.survival || [];
            var days = uniq(att, 'day').map(Number).sort(function (a, b) { return a - b; });
            var members = uniq(att, 'member');
            draw('ws-chart-attention', 'bar', days, perMember(att, 'share', days, members), {scales: {x: {stacked: true}, y: {stacked: true, max: 1}}});
            var mig = t.migration_flows || [], pairs = {};
            mig.forEach(function (r) { var k = r.from_member + ' → ' + r.to_member; pairs[k] = (pairs[k] || 0) + r.n; });
            draw('ws-chart-migration', 'bar', Object.keys(pairs), [{label: '#', backgroundColor: COLORS[0], data: Object.keys(pairs).map(function (k) { return pairs[k]; })}]);
            var cp = t.crosspost_flows || [], cpDays = uniq(cp, 'day').map(Number).sort(function (a, b) { return a - b; }), cpPairs = {};
            cp.forEach(function (r) { cpPairs[r.source + ' → ' + r.target] = 1; });
            draw('ws-chart-crosspost', 'bar', cpDays, Object.keys(cpPairs).sort().map(function (k, i) {
                return {label: k, backgroundColor: COLORS[i % COLORS.length], data: cpDays.map(function (d) {
                    return cp.filter(function (r) { return r.day === d && (r.source + ' → ' + r.target) === k; }).reduce(function (s, r) { return s + r.n; }, 0); })};
            }), {scales: {x: {stacked: true}, y: {stacked: true}}});
            var body = $('#ws-an-cascades tbody');
            body.textContent = '';
            (t.cascades || []).slice().sort(function (a, b) { return b.size - a.size; }).slice(0, 20).forEach(function (r) {
                var tr = document.createElement('tr');
                [r.source_ref, r.origin, r.day, r.size, r.targets].forEach(function (v) { var td = document.createElement('td'); td.textContent = v; tr.appendChild(td); });
                body.appendChild(tr);
            });
            var sd = t.share_depth || [];
            draw('ws-chart-sharedepth', 'bar', sd.map(function (r) { return r.depth; }), [{label: '#', backgroundColor: COLORS[3], data: sd.map(function (r) { return r.shares; })}]);
            fill('#ws-an-bridges', t.bridge_agents || [], ['agent', 'shares', 'origins', 'destinations'], 20);
            fill('#ws-an-humans', t.human_activity || [], ['human', 'crossposts', 'shares', 'origins', 'destinations', 'first_day', 'last_day'], 20);
            fill('#ws-an-diffusion', t.topic_diffusion || [], ['topic', 'platforms', 'carried', 'created_on', 'first_day', 'last_day'], 30);
            fill('#ws-an-created', t.topics_created || [], ['topic', 'member', 'day', 'source', 'original'], 30);
            fill('#ws-an-topics', (t.topics_carried || []).slice().sort(function (a, b) { return b.n - a.n; }), ['topic', 'source', 'target', 'n', 'first_day'], 30);
            var sDays = uniq(sur, 'day').map(Number).sort(function (a, b) { return a - b; });
            draw('ws-chart-survival', 'line', sDays, perMember(sur, 'survival', sDays, uniq(sur, 'member')), {scales: {y: {min: 0}}});
        }
        function load() {
            if (loaded) { return; }
            loaded = true;
            fetch(box.dataset.url, {credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(render).catch(function () { loaded = false; });
        }
        $all('[data-ws-tab="analytics"]').forEach(function (b) { b.addEventListener('click', load); });
        if (!box.hidden || (location.hash || '') === '#analytics') { load(); }
    }

    /* ---------------------------------------------------------------- parameter form */
    function initContentChoice() {
        var box = document.getElementById('ws-crosspost-content');
        if (!box) { return; }
        var all = $('input[value="all"]', box);
        var others = $all('input[name="crosspost_content"]:not([value="all"])', box);
        function sync() { others.forEach(function (o) { if (all.checked) { o.checked = false; } o.disabled = all.checked; }); }
        all.addEventListener('change', sync);
        others.forEach(function (o) { o.addEventListener('change', function () { if (o.checked) { all.checked = false; sync(); } }); });
    }

    function initDependencies() {
        var mode = document.getElementById('opt__crosspost__mode');
        var probability = document.getElementById('ws-crosspost-probability');
        if (mode && probability) {
            var sync = function () { probability.hidden = mode.value === 'agent_action'; };
            mode.addEventListener('change', sync); sync();
        }
        var initial = document.getElementById('ws-membership-initial');
        var custom = document.getElementById('ws-membership-custom');
        if (initial && custom) {
            var syncInitial = function () { custom.hidden = initial.value !== 'custom'; };
            initial.addEventListener('change', syncInitial); syncInitial();
        }
        var attention = document.getElementById('attention_enabled');
        var leave = document.getElementById('leave_enabled');
        if (attention && leave) {
            var syncLeave = function () {
                if (!attention.checked) { leave.checked = false; }
                leave.disabled = !attention.checked || !!attention.disabled;
            };
            attention.addEventListener('change', syncLeave); syncLeave();
        }
    }

    /* ---------------------------------------------------------------- creation page */
    function initCreate() {
        var form = document.getElementById('world-simulation-form');
        var pick = document.getElementById('ws-members-pick');
        if (!form || !pick) { return; }
        var boxes = $all('input[name="experiments"]', pick);
        var list = document.getElementById('ws-summary-list');
        var count = document.getElementById('ws-summary-count');
        function update() {
            var chosen = boxes.filter(function (b) { return b.checked; });
            var platforms = chosen.map(function (b) { return b.dataset.platform; });
            $all('.ws-platform-card', pick).forEach(function (card) {
                card.classList.toggle('has-choice', platforms.indexOf(card.dataset.platform) >= 0);
            });
            list.textContent = '';
            if (!chosen.length) {
                var li = document.createElement('li'); li.className = 'ws-sub'; li.textContent = form.dataset.textNone; list.appendChild(li);
            }
            chosen.forEach(function (b) {
                var card = b.closest('.ws-platform-card');
                var li = document.createElement('li');
                var icon = card.querySelector('.mdi').cloneNode(true);
                var label = document.createElement('span'); label.textContent = card.querySelector('.ws-name').textContent + ': ' + b.dataset.name;
                li.appendChild(icon); li.appendChild(label); list.appendChild(li);
            });
            count.textContent = (form.dataset.textCount || '').replace('{n}', chosen.length);
            /* the matrices only offer the chosen platforms; the unchosen ones are not submitted */
            var any = chosen.length > 0;
            $all('[data-platform]', form).forEach(function (el) {
                if (pick.contains(el)) { return; }
                var on = !any || platforms.indexOf(el.dataset.platform) >= 0;
                el.hidden = !on;
                $all('input', el).forEach(function (i) { i.disabled = !on; });
                if (el.tagName === 'INPUT') { el.disabled = !on; }
            });
            var matrix = document.getElementById('ws-probability-matrix');
            if (matrix) {
                $all('td input', matrix).forEach(function (i) {
                    var parts = i.name.split('__');
                    i.disabled = any && (platforms.indexOf(parts[1]) < 0 || platforms.indexOf(parts[2]) < 0);
                });
            }
            $all('#ws-provisioning input[type="checkbox"]', form).forEach(function (i) {
                i.disabled = any && platforms.indexOf(i.value) < 0;
                if (i.disabled) { i.checked = false; }
            });
        }
        boxes.forEach(function (b) {
            b.addEventListener('change', function () {
                if (b.checked) {
                    boxes.forEach(function (o) { if (o !== b && o.dataset.platform === b.dataset.platform) { o.checked = false; } });
                }
                update();
            });
        });
        update();
    }

    function start() {
        initTabs();
        initStatus();
        initAnalytics();
        initContentChoice();
        initDependencies();
        initCreate();
    }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', start); } else { start(); }
}());
