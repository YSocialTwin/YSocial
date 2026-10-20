/* Grid.js ships English texts for its own controls (search box, pager, empty and error states).
 * This wrapper gives every grid the active interface language, unless a grid sets its own `language`. */
(function () {
  function install() {
    if (!window.gridjs || !window.gridjs.Grid || window.gridjs.Grid.__ysI18n) { return; }
    var Original = window.gridjs.Grid;
    function localized() {
      return {
        search: { placeholder: YI18n.t('Type a keyword...') },
        pagination: {
          previous: YI18n.t('Previous'),
          next: YI18n.t('Next'),
          navigate: function (page, pages) { return YI18n.t('Page {page} of {pages}', { page: page, pages: pages }); },
          page: function (page) { return YI18n.t('Page {page}', { page: page }); },
          showing: YI18n.t('Showing'),
          of: YI18n.t('of'),
          to: YI18n.t('to'),
          results: YI18n.t('results')
        },
        loading: YI18n.t('Loading...'),
        noRecordsFound: YI18n.t('No matching records found'),
        error: YI18n.t('An error happened while fetching the data')
      };
    }
    function Wrapped(config) {
      var merged = Object.assign({}, config || {});
      var base = localized(), own = merged.language || {};
      merged.language = Object.assign({}, base, own, {
        search: Object.assign({}, base.search, own.search || {}),
        pagination: Object.assign({}, base.pagination, own.pagination || {})
      });
      return new Original(merged);
    }
    Wrapped.prototype = Original.prototype;
    Wrapped.__ysI18n = true;
    try { window.gridjs.Grid = Wrapped; } catch (e) { /* read-only build: grids stay in English */ }
  }
  install();
  document.addEventListener('DOMContentLoaded', install);
})();
