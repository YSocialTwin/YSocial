/* Browser-side translations.
 *
 *   YI18n.t('login.show_password')                      -> string
 *   YI18n.t('login.continue_to', {name: 'X'})           -> placeholders {name}
 *   YI18n.tn('posts.count', 3, {topic: 'x'})            -> plural, {count} is added
 *   YI18n.formatNumber(1234.5) / YI18n.formatDate(date) -> Intl, active language
 *
 * Catalogs come from /i18n/<domain>/<lang>.json (symbolic keys, English fallback).
 * A plural entry is an object: {"one": "{count} post", "other": "{count} posts"};
 * the categories follow Intl.PluralRules for the page language (<html lang>).
 */
(function () {
  'use strict';
  var catalogs = {};
  var lang = document.documentElement.getAttribute('lang') || 'en';
  var rules = null;
  try { rules = new Intl.PluralRules(lang); } catch (e) { rules = null; }

  function format(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (m, k) {
      return params && params[k] !== undefined ? params[k] : m;
    });
  }

  function lookup(key) {
    for (var d in catalogs) {
      if (Object.prototype.hasOwnProperty.call(catalogs[d], key)) {
        return catalogs[d][key];
      }
    }
    return undefined;
  }

  function t(key, params) {
    var entry = lookup(key);
    if (entry === undefined) { return format(key, params); }
    if (typeof entry === 'object') { entry = entry.other !== undefined ? entry.other : key; }
    return format(entry, params);
  }

  function tn(key, count, params) {
    var merged = { count: count };
    for (var k in params) { if (Object.prototype.hasOwnProperty.call(params, k)) { merged[k] = params[k]; } }
    var entry = lookup(key);
    if (entry === undefined) { return format(key, merged); }
    if (typeof entry === 'string') { return format(entry, merged); }
    var category = rules ? rules.select(count) : (count === 1 ? 'one' : 'other');
    var text = entry[category] !== undefined ? entry[category] : entry.other;
    return format(text !== undefined ? text : key, merged);
  }

  function formatNumber(value, options) { return new Intl.NumberFormat(lang, options).format(value); }
  function formatDate(value, options) {
    return new Intl.DateTimeFormat(lang, options || { dateStyle: 'medium' }).format(value instanceof Date ? value : new Date(value));
  }

  function load(domain) {
    return fetch('/i18n/' + domain + '/' + lang + '.json', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (data) { catalogs[domain] = data; return data; })
      .catch(function () { return {}; });
  }

  var ready = load('core');
  window.YI18n = {
    t: t, tn: tn, load: load, ready: ready, lang: lang,
    formatNumber: formatNumber, formatDate: formatDate
  };
})();
