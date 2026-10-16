/* Browser-side translations: window.YI18n.t('key', {name: 'x'}).
   Catalogs come from /i18n/<domain>/<lang>.json (symbolic keys, English fallback). */
(function () {
  'use strict';
  var catalogs = {};
  var lang = document.documentElement.getAttribute('lang') || 'en';

  function format(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (m, k) {
      return params && params[k] !== undefined ? params[k] : m;
    });
  }

  function t(key, params) {
    for (var d in catalogs) {
      if (Object.prototype.hasOwnProperty.call(catalogs[d], key)) {
        return format(catalogs[d][key], params);
      }
    }
    return format(key, params);
  }

  function load(domain) {
    return fetch('/i18n/' + domain + '/' + lang + '.json', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (data) { catalogs[domain] = data; return data; })
      .catch(function () { return {}; });
  }

  var ready = load('core');
  window.YI18n = { t: t, load: load, ready: ready, lang: lang };
})();
