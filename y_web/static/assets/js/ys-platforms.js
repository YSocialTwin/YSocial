/* What each installed platform calls itself and how its badge is styled.
 * The data is declared by the platforms and handed over as attributes on <html>. */
(function () {
    var root = document.documentElement;
    var catalog = {};
    try {
        catalog = JSON.parse(root.getAttribute('data-ys-platforms') || '{}');
    } catch (e) {
        catalog = {};
    }
    window.YS_PLATFORMS = catalog;
    window.YS_DEFAULT_PLATFORM = root.getAttribute('data-ys-default-platform') || '';
    window.ysPlatform = function (key) {
        var plain = String(key || '').replace(/[_-]+/g, ' ');
        return window.YS_PLATFORMS[key] || { label: plain, badge_text: plain, badge: key, icon: '' };
    };
})();
