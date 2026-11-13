(function () {
    var buttons = document.querySelectorAll('[data-platform-filter]');
    if (!buttons.length) return;
    var items = document.querySelectorAll('[data-agent-resource-item]');
    function apply(key) {
        buttons.forEach(function (b) {
            b.classList.toggle('is-active', b.dataset.platformFilter === key);
        });
        items.forEach(function (item) {
            var on = key === 'all' || (' ' + item.dataset.platforms + ' ').indexOf(' ' + key + ' ') !== -1;
            item.style.display = on ? '' : 'none';
        });
        try { sessionStorage.setItem('ys-agents-platform', key); } catch (e) {}
    }
    buttons.forEach(function (b) {
        b.addEventListener('click', function () { apply(b.dataset.platformFilter); });
    });
    var saved = 'all';
    try { saved = sessionStorage.getItem('ys-agents-platform') || 'all'; } catch (e) {}
    apply(Array.prototype.some.call(buttons, function (b) { return b.dataset.platformFilter === saved; }) ? saved : 'all');
})();
