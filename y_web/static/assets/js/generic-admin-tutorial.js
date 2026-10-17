/**
 * Guided tour for every admin page that has no dedicated tutorial script.
 *
 * Frame steps (sidebar, toolbar) + the steps of the page (``admin-pages-tutorial.js``) +
 * every other marked box of the page, described from its own help text. Titles taken
 * from the page are already translated; fixed texts are English keys of the
 * ``tutorials`` catalog.
 */
(function () {
    var FALLBACK = window.YS_PAGE_TUTORIAL_FALLBACK || { title: 'Overview', description: 'Review and edit the values in this section.' };

    function visible(el) {
        return !!(el && el.getClientRects && el.getClientRects().length);
    }

    function textOf(el) {
        return (el && el.textContent ? el.textContent : '').replace(/\s+/g, ' ').trim();
    }

    function headingOf(box) {
        var h = box.querySelector('h1, h2, h3, h4, .title');
        return textOf(h);
    }

    function helpOf(box) {
        var p = box.querySelector('.help-block p, .group-helper-text, .ys-text-small, p');
        var t = textOf(p);
        return t.length > 220 ? t.slice(0, 217).replace(/\s+\S*$/, '') + '…' : t;
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function frameSteps() {
        var steps = [];
        if (document.querySelector('.dashboard-aside')) {
            steps.push({ id: 'sidebar', selector: '.dashboard-aside', title: 'Sidebar Navigation',
                description: 'Use the sidebar to move between experiment setup, users, agents, and system tooling.', position: 'right' });
        }
        if (document.querySelector('.dashboard-toolbar')) {
            steps.push({ id: 'toolbar', selector: '.dashboard-toolbar', title: 'Top Toolbar',
                description: 'The top toolbar hosts quick actions such as replay tutorial, account shortcuts, and active simulation access.', position: 'bottom' });
        }
        return steps;
    }

    function pageSteps(page) {
        var defs = (window.YS_PAGE_TUTORIALS || {})[page] || [];
        var steps = [];
        var described = {};
        defs.forEach(function (def, index) {
            var el = null;
            try { el = document.querySelector(def.selector); } catch (e) { el = null; }
            if (!el || !visible(el)) return;
            described[def.selector] = true;
            var title = def.title;
            if (title === '@heading') title = headingOf(el) || FALLBACK.title;
            steps.push({ id: page + '-' + index, selector: def.selector, title: title, description: def.description,
                position: def.position === 'auto' ? autoPosition(el) : def.position });
        });
        // Boxes the page marks but the tour does not describe still get a step.
        Array.prototype.forEach.call(document.querySelectorAll('[data-tut]'), function (box) {
            var selector = '[data-tut="' + box.getAttribute('data-tut') + '"]';
            if (described[selector] || !visible(box)) return;
            var help = helpOf(box);
            steps.push({ id: page + '-' + box.getAttribute('data-tut'), selector: selector, title: headingOf(box) || FALLBACK.title,
                description: help ? '<p>' + escapeHtml(help) + '</p>' : FALLBACK.description, position: autoPosition(box) });
        });
        return steps;
    }

    // tall elements: the tooltip sits over them, short ones: below
    function autoPosition(el) {
        return el.getBoundingClientRect().height > window.innerHeight * 0.55 ? 'overlay' : 'bottom';
    }

    function pickSteps() {
        var holder = document.querySelector('[data-tutorial-page]');
        var page = holder ? holder.getAttribute('data-tutorial-page') : '';
        var steps = frameSteps();
        var own = page ? pageSteps(page) : [];

        if (own.length) {
            steps = steps.concat(own);
        } else {
            if (document.querySelector('.dashboard-body .dashboard-box')) {
                steps.push({ id: 'main-content', selector: '.dashboard-body .dashboard-box', title: 'Main Content Panel',
                    description: 'This panel contains the primary controls and outputs for the current admin page.', position: 'top' });
            }
            if (document.querySelector('form')) {
                steps.push({ id: 'forms', selector: 'form', title: 'Form Actions',
                    description: 'Most pages apply changes through forms. Review required fields before submitting to avoid partial updates.', position: 'top' });
            }
        }
        if (document.querySelector('#tutorial-replay-btn')) {
            steps.push({ id: 'replay', selector: '#tutorial-replay-btn', title: 'Replay Tutorial',
                description: 'You can reopen this guide at any time from the help button in the header.', position: 'bottom' });
        }
        steps.forEach(function (s) { s.isLast = false; });
        if (steps.length) steps[steps.length - 1].isLast = true;
        return steps;
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!window.PageTutorialEngine) return;
        // One engine, one set of listeners; the shared array is refilled at every start.
        var shared = [];
        var tutorial = window.PageTutorialEngine.init('admin_generic', shared);
        if (!tutorial) return;
        window.startGenericAdminTutorial = function () {
            shared.length = 0;
            pickSteps().forEach(function (step) { shared.push(step); });
            if (shared.length) tutorial.start();
        };
    });
})();
