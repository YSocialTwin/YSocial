/**
 * Charts of the custom fields of a population (page admin/population_details), drawn with Chart.js like the
 * demographic charts of the same page. Groups are <details>: a chart is created when its group is open, so the
 * canvases of a closed group never get a zero size.
 */
(function () {
  'use strict';
  var groups = window.YS_CUSTOM_FIELDS;
  if (!groups || !groups.length || typeof Chart === 'undefined') { return; }

  var t = function (text) { return (window.YI18n && YI18n.t) ? YI18n.t(text) : text; };
  // the platforms give the palette of their custom fields (window.YS_PLATFORMS); the others use this one
  var DEFAULT_PALETTE = ['#8b5cf6', '#a78bfa', '#c4b5fd', '#7c3aed', '#6d28d9', '#ddd6fe', '#5b21b6', '#a5b4fc'];
  function paletteOf(badge) {
    var found = Object.keys(window.YS_PLATFORMS || {}).map(function (k) { return window.YS_PLATFORMS[k]; }).filter(function (p) {
      return p.badge === badge && p.palette && p.palette.length;
    })[0];
    return found ? found.palette : DEFAULT_PALETTE;
  }

  var built = {};

  function colours(group, n) {
    var base = paletteOf(group.badge), out = [];
    for (var i = 0; i < n; i++) { out.push(base[i % base.length]); }
    return out;
  }

  function labelsOf(block) {
    if (block.kind !== 'flag') { return block.labels; }
    return block.labels.map(function (l) { return l === 'yes' ? t('Yes') : (l === 'no' ? t('No') : l); });
  }

  function config(group, block) {
    var labels = labelsOf(block), n = labels.length;
    var round = block.kind === 'flag' || (block.kind === 'categorical' && n <= 4);
    var horizontal = block.kind === 'categorical' && n > 6;
    var shades = colours(group, n);
    var dataset = {
      label: t('Agents'),
      data: block.data,
      backgroundColor: round || block.kind === 'categorical' ? shades : shades[0] + 'cc',
      borderColor: round ? '#ffffff' : (block.kind === 'categorical' ? shades : shades[0]),
      borderWidth: round ? 2 : 1
    };
    var options = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: round, position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } } };
    if (!round) {
      options.indexAxis = horizontal ? 'y' : 'x';
      options.scales = {
        x: { ticks: { font: { size: 10 }, maxRotation: horizontal ? 0 : 45, minRotation: horizontal ? 0 : (block.kind === 'numeric' ? 30 : 0) }, beginAtZero: true },
        y: { ticks: { font: { size: 10 }, precision: 0 }, beginAtZero: true }
      };
      if (!horizontal) { options.scales.x.beginAtZero = false; }
      options.plugins.legend.display = false;
    }
    return { type: round ? 'doughnut' : 'bar', data: { labels: labels, datasets: [dataset] }, options: options };
  }

  function drawGroup(group) {
    if (built[group.id]) { return; }
    built[group.id] = true;
    group.blocks.forEach(function (block, index) {
      var canvas = document.getElementById('cf_' + group.id + '_' + index);
      if (canvas) { new Chart(canvas, config(group, block)); }
    });
  }

  groups.forEach(function (group) {
    var box = document.getElementById('cf-' + group.id);
    if (!box) { return; }
    if (box.open) { drawGroup(group); }
    box.addEventListener('toggle', function () { if (box.open) { drawGroup(group); } });
  });

  // a chip of the index opens its group and scrolls to it
  document.querySelectorAll('.ys-cf-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var target = document.querySelector(chip.getAttribute('href'));
      if (target && target.tagName === 'DETAILS') { target.open = true; }
    });
  });
})();
