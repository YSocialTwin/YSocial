(function () {
  function sanitizeFilename(value) {
    return String(value || 'chart')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'chart';
  }

  function getChartForTarget(target) {
    var canvas = target ? target.querySelector('canvas') : null;
    if (!canvas || typeof Chart === 'undefined' || typeof Chart.getChart !== 'function') {
      return null;
    }
    return Chart.getChart(canvas) || null;
  }

  function resizeChartForTarget(target) {
    var chart = getChartForTarget(target);
    if (!chart) return;
    try {
      if (chart.canvas) {
        chart.canvas.style.width = '';
        chart.canvas.style.height = '';
      }
      chart.resize();
    } catch (e) {}
  }

  function scheduleResizeForTarget(target) {
    if (!target) return;
    resizeChartForTarget(target);
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(function () {
        resizeChartForTarget(target);
        window.requestAnimationFrame(function () {
          resizeChartForTarget(target);
        });
      });
    }
    window.setTimeout(function () {
      resizeChartForTarget(target);
    }, 40);
    window.setTimeout(function () {
      resizeChartForTarget(target);
    }, 140);
  }

  function buildFilledDataUrl(canvas, mimeType, quality) {
    var exportCanvas = document.createElement('canvas');
    exportCanvas.width = canvas.width;
    exportCanvas.height = canvas.height;
    var ctx = exportCanvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
    ctx.drawImage(canvas, 0, 0);
    return exportCanvas.toDataURL(mimeType, quality || 0.95);
  }

  function triggerDownload(dataUrl, filename) {
    var link = document.createElement('a');
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  function exportChart(target, format) {
    var canvas = target ? target.querySelector('canvas') : null;
    if (!canvas) return;
    var filenameBase = sanitizeFilename(target.getAttribute('data-chart-filename') || target.id || 'chart');
    if (format === 'png') {
      triggerDownload(canvas.toDataURL('image/png'), filenameBase + '.png');
      return;
    }
    if (format === 'jpg') {
      triggerDownload(buildFilledDataUrl(canvas, 'image/jpeg', 0.95), filenameBase + '.jpg');
      return;
    }
    if (format === 'pdf') {
      if (!window.jspdf || !window.jspdf.jsPDF) return;
      var width = canvas.width || 1200;
      var height = canvas.height || 800;
      var orientation = width >= height ? 'landscape' : 'portrait';
      var pdf = new window.jspdf.jsPDF({
        orientation: orientation,
        unit: 'pt',
        format: [width, height]
      });
      var imageData = buildFilledDataUrl(canvas, 'image/jpeg', 0.98);
      pdf.addImage(imageData, 'JPEG', 0, 0, width, height);
      pdf.save(filenameBase + '.pdf');
    }
  }

  function ensureToolbar(target) {
    var existing = target.querySelector('.ys-chart-fullscreen-toolbar');
    if (existing) return existing;
    var toolbar = document.createElement('div');
    toolbar.className = 'ys-chart-fullscreen-toolbar';
    toolbar.innerHTML = '' +
      '<button type="button" class="ys-chart-toolbar-button" data-export-format="png">PNG</button>' +
      '<button type="button" class="ys-chart-toolbar-button" data-export-format="jpg">JPG</button>' +
      '<button type="button" class="ys-chart-toolbar-button" data-export-format="pdf">PDF</button>' +
      '<button type="button" class="ys-chart-toolbar-button is-close" data-chart-close="1">Close</button>';
    toolbar.addEventListener('click', function (event) {
      var button = event.target.closest('.ys-chart-toolbar-button');
      if (!button) return;
      if (button.hasAttribute('data-chart-close')) {
        collapseTarget(target);
        return;
      }
      var format = button.getAttribute('data-export-format');
      if (format) exportChart(target, format);
    });
    target.appendChild(toolbar);
    return toolbar;
  }

  function updateButtonState(button, isActive) {
    if (!button) return;
    button.classList.toggle('is-active', isActive);
    button.title = isActive ? 'Collapse plot' : 'Expand plot';
    var icon = button.querySelector('i');
    if (icon) {
      icon.className = isActive ? 'mdi mdi-fullscreen-exit' : 'mdi mdi-fullscreen';
    }
  }

  function collapseTarget(target) {
    if (!target) return;
    target.classList.remove('is-fullscreen');
    document.body.classList.remove('ys-chart-fullscreen-active');
    target.style.width = '';
    target.style.minWidth = '';
    target.style.maxWidth = '';
    target.style.height = '';
    target.style.minHeight = '';
    target.style.maxHeight = '';
    var button = document.querySelector('.annotation-chart-expand-button[data-fullscreen-target="' + target.id + '"]');
    updateButtonState(button, false);
    scheduleResizeForTarget(target);
  }

  function expandTarget(target) {
    if (!target) return;
    document.querySelectorAll('.ys-chart-fullscreen-target.is-fullscreen').forEach(function (node) {
      if (node !== target) collapseTarget(node);
    });
    target.classList.add('is-fullscreen');
    document.body.classList.add('ys-chart-fullscreen-active');
    ensureToolbar(target);
    var button = document.querySelector('.annotation-chart-expand-button[data-fullscreen-target="' + target.id + '"]');
    updateButtonState(button, true);
    scheduleResizeForTarget(target);
  }

  function bindButtons() {
    document.querySelectorAll('.annotation-chart-expand-button[data-fullscreen-target]').forEach(function (button) {
      if (button.dataset.fullscreenBound === '1') return;
      button.dataset.fullscreenBound = '1';
      button.addEventListener('click', function () {
        var targetId = button.getAttribute('data-fullscreen-target');
        var target = document.getElementById(targetId);
        if (!target) return;
        if (target.classList.contains('is-fullscreen')) {
          collapseTarget(target);
        } else {
          expandTarget(target);
        }
      });
    });
  }

  function init() {
    bindButtons();
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      var target = document.querySelector('.ys-chart-fullscreen-target.is-fullscreen');
      if (target) collapseTarget(target);
    });
    window.addEventListener('resize', function () {
      var target = document.querySelector('.ys-chart-fullscreen-target.is-fullscreen');
      if (target) scheduleResizeForTarget(target);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
