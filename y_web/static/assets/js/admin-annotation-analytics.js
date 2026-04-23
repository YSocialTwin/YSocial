(function () {
  var config = window.YS_DATA_ANNOTATION_ANALYTICS || {};
  if (!config.expId) return;

  var state = {
    currentDay: Number(config.filterDay || 1),
    currentHour: Number(config.filterHour || 1),
    maxTick: Number(config.maxTick || 24),
    currentAnalytics: config.analytics || {},
    currentGranularity: 'hourly',
    playing: false,
    speedIndex: 0,
    speedMultipliers: [1, 2, 4, 8],
    timer: null
  };

  var distributionChart = null;
  var trendChart = null;
  var secondaryChart = null;
  var componentShareChart = null;
  var networkStructureChart = null;
  var egoNetworkChart = null;
  var topicLifecycleChart = null;
  var moderatorTargetChart = null;
  var recsysAuthorReachChart = null;
  var recsysAuthorReceiverDiversityChart = null;
  var recsysAuthorDistributionChart = null;

  function allCharts() {
    return [
      distributionChart,
      trendChart,
      secondaryChart,
      componentShareChart,
      networkStructureChart,
      egoNetworkChart,
      topicLifecycleChart,
      moderatorTargetChart,
      recsysAuthorReachChart,
      recsysAuthorReceiverDiversityChart,
      recsysAuthorDistributionChart
    ].filter(Boolean);
  }

  function resizeAllCharts() {
    allCharts().forEach(function (chart) {
      try { chart.resize(); } catch (e) {}
    });
  }

  function mixHeatColor(start, end, intensity) {
    var t = Math.max(0, Math.min(1, Number(intensity || 0)));
    var r = Math.round(start[0] + (end[0] - start[0]) * t);
    var g = Math.round(start[1] + (end[1] - start[1]) * t);
    var b = Math.round(start[2] + (end[2] - start[2]) * t);
    return 'rgba(' + r + ', ' + g + ', ' + b + ', 0.96)';
  }

  var egoEdgePlugin = {
    id: 'ysEgoEdgePlugin',
    beforeDatasetsDraw: function (chart, args, pluginOptions) {
      if (!pluginOptions || !pluginOptions.edges || !pluginOptions.edges.length) return;
      var xScale = chart.scales.x;
      var yScale = chart.scales.y;
      if (!xScale || !yScale) return;
      var ctx = chart.ctx;
      var nodeLookup = pluginOptions.nodeLookup || {};
      ctx.save();
      (pluginOptions.edges || []).forEach(function (edge) {
        var sourceNode = nodeLookup[edge.source] || {};
        var targetNode = nodeLookup[edge.target] || {};
        var touchesEgo = !!sourceNode.is_ego || !!targetNode.is_ego;
        var activeEdge = !!sourceNode.is_active && !!targetNode.is_active;
        var controlX = (edge.x1 + edge.x2) / 2;
        var controlY = (edge.y1 + edge.y2) / 2;
        if (!touchesEgo) {
          var dx = edge.x2 - edge.x1;
          var dy = edge.y2 - edge.y1;
          var magnitude = Math.sqrt((dx * dx) + (dy * dy)) || 1;
          controlX += (-dy / magnitude) * 0.08;
          controlY += (dx / magnitude) * 0.08;
        }
        ctx.beginPath();
        ctx.strokeStyle = touchesEgo
          ? (activeEdge ? 'rgba(59, 130, 246, 0.44)' : 'rgba(148, 163, 184, 0.3)')
          : (activeEdge ? 'rgba(148, 163, 184, 0.5)' : 'rgba(203, 213, 225, 0.28)');
        ctx.lineWidth = touchesEgo ? 2.1 : 1.35;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(xScale.getPixelForValue(edge.x1), yScale.getPixelForValue(edge.y1));
        ctx.quadraticCurveTo(
          xScale.getPixelForValue(controlX),
          yScale.getPixelForValue(controlY),
          xScale.getPixelForValue(edge.x2),
          yScale.getPixelForValue(edge.y2)
        );
        ctx.stroke();
      });
      ctx.restore();
    }
  };
  var egoLabelPlugin = {
    id: 'ysEgoLabelPlugin',
    afterDatasetsDraw: function (chart, args, pluginOptions) {
      if (!pluginOptions || !pluginOptions.nodes || !pluginOptions.nodes.length) return;
      var maxVisibleLabels = Number(pluginOptions.maxVisibleLabels || 18);
      if ((pluginOptions.nodes || []).length > maxVisibleLabels) return;
      var xScale = chart.scales.x;
      var yScale = chart.scales.y;
      if (!xScale || !yScale) return;
      var ctx = chart.ctx;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      (pluginOptions.nodes || []).forEach(function (node) {
        var label = String(node.label || '');
        if (!label) return;
        var x = xScale.getPixelForValue(Number(node.x || 0));
        var y = yScale.getPixelForValue(Number(node.y || 0));
        var text = label.length > 18 ? (label.slice(0, 17) + '…') : label;
        ctx.font = (node.is_ego ? '600 11px Inter, system-ui, sans-serif' : '500 10px Inter, system-ui, sans-serif');
        var metrics = ctx.measureText(text);
        var paddingX = node.is_ego ? 9 : 7;
        var paddingY = node.is_ego ? 6 : 5;
        var width = metrics.width + (paddingX * 2);
        var height = (node.is_ego ? 24 : 21);
        var rectX = x - (width / 2);
        var rectY = y + (node.is_ego ? 18 : 15);
        ctx.fillStyle = node.is_ego ? 'rgba(255, 245, 245, 0.96)' : 'rgba(255, 255, 255, 0.92)';
        ctx.strokeStyle = node.is_ego ? 'rgba(239, 68, 68, 0.34)' : 'rgba(203, 213, 225, 0.9)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(rectX, rectY, width, height, 999);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = node.is_ego ? '#991b1b' : '#475569';
        ctx.fillText(text, x, rectY + (height / 2) + 0.5);
      });
      ctx.restore();
    }
  };
  var heatmapCellPlugin = {
    id: 'ysHeatmapCellPlugin',
    beforeDatasetsDraw: function (chart, args, pluginOptions) {
      if (!pluginOptions || !pluginOptions.enabled) return;
      var xScale = chart.scales.x;
      var yScale = chart.scales.y;
      var dataset = (((chart.data || {}).datasets || [])[0]) || null;
      if (!xScale || !yScale || !dataset) return;
      var ctx = chart.ctx;
      var rowCount = Math.max(Number(pluginOptions.rowCount || 0), 1);
      var colCount = Math.max(Number(pluginOptions.colCount || 0), 1);
      var chartArea = chart.chartArea;
      if (!chartArea) return;
      var colWidth = (chartArea.right - chartArea.left) / colCount;
      var rowHeight = (chartArea.bottom - chartArea.top) / rowCount;
      var xGap = Math.min(0.9, colWidth * 0.06);
      var yGap = Math.min(4, Math.max(1.25, rowHeight * 0.18));

      ctx.save();
      (dataset.data || []).forEach(function (raw) {
        var centerX = xScale.getPixelForValue(Number(raw.x || 0));
        var centerY = yScale.getPixelForValue(Number(raw.y || 0));
        var fill = typeof pluginOptions.getBackgroundColor === 'function'
          ? pluginOptions.getBackgroundColor(raw)
          : 'rgba(37, 99, 235, 0.9)';
        ctx.fillStyle = fill;
        ctx.fillRect(
          centerX - (colWidth / 2) + (xGap / 2),
          centerY - (rowHeight / 2) + (yGap / 2),
          Math.max(1, colWidth - xGap),
          Math.max(1, rowHeight - yGap)
        );
      });
      ctx.restore();
    }
  };
  if (typeof Chart !== 'undefined') {
    try { Chart.register(egoEdgePlugin); } catch (e) {}
    try { Chart.register(egoLabelPlugin); } catch (e) {}
    try { Chart.register(heatmapCellPlugin); } catch (e) {}
  }

  function withAlpha(color, alpha) {
    if (!color || typeof color !== 'string') return color;
    if (color.startsWith('rgba(') || color.startsWith('hsla(')) return color;
    if (color.startsWith('#')) {
      var hex = color.replace('#', '');
      if (hex.length === 3) {
        hex = hex.split('').map(function (c) { return c + c; }).join('');
      }
      if (hex.length === 6) {
        var r = parseInt(hex.slice(0, 2), 16);
        var g = parseInt(hex.slice(2, 4), 16);
        var b = parseInt(hex.slice(4, 6), 16);
        return 'rgba(' + r + ', ' + g + ', ' + b + ', ' + alpha + ')';
      }
    }
    return color;
  }

  function buildDatasets(datasets, fallbackType) {
    return (datasets || []).map(function (dataset, index) {
      var border = dataset.borderColor || dataset.backgroundColor || '#2563eb';
      var background = dataset.backgroundColor;
      if (!background && (dataset.type || fallbackType) === 'line') {
        background = withAlpha(border, 0.18);
      }
      return Object.assign({
        borderWidth: 2,
        pointRadius: 2,
        pointHoverRadius: 4,
        tension: 0.25
      }, dataset, {
        type: dataset.type || fallbackType,
        borderColor: border,
        backgroundColor: background || withAlpha(border, 0.45)
      });
    });
  }

  function chartOptions(definition) {
    var extra = definition.options || {};
    var stacked = !!extra.stacked;
    var yScale = {
      type: extra.yType || 'linear',
      beginAtZero: !!extra.beginAtZero
    };
    var xScale = {
      type: extra.xType || 'category',
      stacked: stacked,
      ticks: { autoSkip: true, maxRotation: 0 }
    };
    if (typeof extra.min === 'number') yScale.min = extra.min;
    if (typeof extra.max === 'number') yScale.max = extra.max;
    if (typeof extra.xMin === 'number') xScale.min = extra.xMin;
    if (typeof extra.xMax === 'number') xScale.max = extra.xMax;
    if (extra.xTitle) xScale.title = { display: true, text: extra.xTitle };
    if (extra.yTitle) yScale.title = { display: true, text: extra.yTitle };
    if (stacked) yScale.stacked = true;
    if (stacked) xScale.stacked = true;
    if (extra.indexAxis === 'y') {
      xScale = {
        type: extra.xType || 'linear',
        beginAtZero: !!extra.beginAtZero
      };
      yScale = {
        type: extra.yType || 'category',
        ticks: { autoSkip: false, maxRotation: 0 }
      };
      if (typeof extra.min === 'number') xScale.min = extra.min;
      if (typeof extra.max === 'number') xScale.max = extra.max;
      if (extra.xTitle) xScale.title = { display: true, text: extra.xTitle };
      if (extra.yTitle) yScale.title = { display: true, text: extra.yTitle };
    }

    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 220 },
      interaction: {
        mode: 'nearest',
        intersect: false
      },
      plugins: {
        legend: {
          display: extra.legendDisplay === false ? false : true,
          position: extra.legendPosition || 'top'
        }
      },
      indexAxis: extra.indexAxis || 'x',
      scales: definition.type === 'doughnut' ? {} : {
        x: xScale,
        y: yScale
      }
    };
  }

  function renderChart(instance, canvasId, definition) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !definition) return instance;
    if (instance) instance.destroy();
    return new Chart(canvas, {
      type: definition.type || 'bar',
      data: {
        labels: definition.labels || [],
        datasets: buildDatasets(definition.datasets || [], definition.type || 'bar')
      },
      options: chartOptions(definition)
    });
  }

  function renderComponentShareChart(definition) {
    return renderChart(componentShareChart, 'annotationComponentShareChart', definition);
  }

  function renderNetworkStructureChart(definition) {
    return renderChart(networkStructureChart, 'annotationNetworkStructureChart', definition);
  }

  function renderTopicLifecycleChart(definition) {
    return renderChart(topicLifecycleChart, 'annotationTopicLifecycleChart', definition);
  }

  function renderModeratorTargetChart(definition) {
    var canvas = document.getElementById('toxModeratorTargetTrendChart');
    if (!canvas || !definition) return moderatorTargetChart;
    if (moderatorTargetChart) moderatorTargetChart.destroy();
    var ctx = canvas.getContext('2d');
    moderatorTargetChart = new Chart(ctx, {
      data: {
        labels: definition.timestamps || [],
        datasets: [
          {
            type: 'line',
            label: 'Average Target Toxicity',
            data: ((definition.datasets || [])[0] || {}).data || [],
            borderColor: 'rgba(14, 165, 233, 1)',
            backgroundColor: 'rgba(14, 165, 233, 0.16)',
            fill: false,
            tension: 0.25,
            yAxisID: 'y'
          },
          {
            type: 'line',
            label: 'Peak Target Toxicity',
            data: ((definition.datasets || [])[1] || {}).data || [],
            borderColor: 'rgba(239, 68, 68, 1)',
            backgroundColor: 'rgba(239, 68, 68, 0.16)',
            borderDash: [6, 4],
            fill: false,
            tension: 0.25,
            yAxisID: 'y'
          },
          {
            type: 'bar',
            label: 'Moderator Actions',
            data: ((definition.datasets || [])[2] || {}).data || [],
            borderColor: 'rgba(16, 185, 129, 1)',
            backgroundColor: 'rgba(16, 185, 129, 0.35)',
            borderWidth: 1,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 0 },
        plugins: {
          legend: { display: true, position: 'bottom' },
          tooltip: {
            callbacks: {
              title: function (context) {
                var key = context[0].label;
                var mapping = (definition.timestamp_mapping || {})[key];
                if (mapping) return 'Day ' + mapping.day + ', Hour ' + mapping.hour;
                return 'Step ' + key;
              },
              label: function (context) {
                if (context.dataset.label === 'Moderator Actions') {
                  return context.dataset.label + ': ' + Number(context.parsed.y || 0).toFixed(0);
                }
                return context.dataset.label + ': ' + Number(context.parsed.y || 0).toFixed(3);
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 1,
            title: { display: true, text: 'Toxicity' }
          },
          y1: {
            beginAtZero: true,
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { precision: 0 },
            title: { display: true, text: 'Moderator Actions' }
          },
          x: {
            title: { display: true, text: 'Simulation Days' }
          }
        }
      }
    });
    return moderatorTargetChart;
  }

  function updateRecsysAuthorSection(panel) {
    var select = document.getElementById('annotation-recsys-author-select');
    if (select) {
      var selected = panel.selected_uid || '';
      var placeholderHtml = '<option value=""' + (selected ? '' : ' selected') + '>Choose an author…</option>';
      select.innerHTML = placeholderHtml + (panel.options || []).map(function (option) {
        var sel = option.uid === selected ? ' selected' : '';
        return '<option value="' + option.uid + '"' + sel + '>' +
          option.username + ' (' + option.recommendation_count + ' recs)' +
          '</option>';
      }).join('');
    }

    var emptyState = document.getElementById('recsys-author-empty-state');
    var statsRow = document.getElementById('recsys-author-stats-row');
    var reachColumn = document.getElementById('recsys-author-reach-column');
    var receiverDiversityColumn = document.getElementById('recsys-author-receiver-diversity-column');
    var distributionColumn = document.getElementById('recsys-author-distribution-column');
    var tableRow = document.getElementById('recsys-author-table-row');
    var hasSelection = !!panel.selected_uid;

    if (emptyState) emptyState.style.display = hasSelection ? 'none' : '';
    if (statsRow) statsRow.style.display = hasSelection ? '' : 'none';
    if (reachColumn) reachColumn.style.display = hasSelection ? '' : 'none';
    if (receiverDiversityColumn) receiverDiversityColumn.style.display = hasSelection ? '' : 'none';
    if (distributionColumn) distributionColumn.style.display = hasSelection ? '' : 'none';
    if (tableRow) tableRow.style.display = hasSelection ? '' : 'none';

    var nameNode = document.getElementById('recsys-author-name');
    var uniqueNode = document.getElementById('recsys-author-unique-recipients');
    var totalNode = document.getElementById('recsys-author-total-recommendations');
    var postsNode = document.getElementById('recsys-author-recommended-posts');
    if (nameNode) nameNode.textContent = panel.selected_username || '—';
    if (uniqueNode) uniqueNode.textContent = panel.unique_recipients || 0;
    if (totalNode) totalNode.textContent = panel.total_recommendations || 0;
    if (postsNode) postsNode.textContent = panel.recommended_posts || 0;

    var reachTitle = document.getElementById('recsys-author-reach-title');
    var reachDescription = document.getElementById('recsys-author-reach-description');
    if (reachTitle && panel.reach_trend) reachTitle.textContent = panel.reach_trend.title || '';
    if (reachDescription && panel.reach_trend) reachDescription.textContent = panel.reach_trend.description || '';
    var distTitle = document.getElementById('recsys-author-distribution-title');
    var distDescription = document.getElementById('recsys-author-distribution-description');
    if (distTitle && panel.post_distribution) distTitle.textContent = panel.post_distribution.title || '';
    if (distDescription && panel.post_distribution) distDescription.textContent = panel.post_distribution.description || '';
    var receiverTitle = document.getElementById('recsys-author-receiver-diversity-title');
    var receiverDescription = document.getElementById('recsys-author-receiver-diversity-description');
    if (receiverTitle && panel.receiver_diversity_trend) receiverTitle.textContent = panel.receiver_diversity_trend.title || '';
    if (receiverDescription && panel.receiver_diversity_trend) receiverDescription.textContent = panel.receiver_diversity_trend.description || '';

    var summaryBody = document.getElementById('recsys-author-summary-body');
    if (summaryBody) {
      summaryBody.innerHTML = (panel.summary_rows || []).map(function (row) {
        return '<tr>' + row.map(function (cell) {
          return '<td>' + String(cell == null ? '' : cell) + '</td>';
        }).join('') + '</tr>';
      }).join('');
    }

    if (hasSelection) {
      recsysAuthorReachChart = renderChart(
        recsysAuthorReachChart,
        'recsysAuthorReachChart',
        panel.reach_trend || null
      );
      recsysAuthorReceiverDiversityChart = renderChart(
        recsysAuthorReceiverDiversityChart,
        'recsysAuthorReceiverDiversityChart',
        panel.receiver_diversity_trend || null
      );
      recsysAuthorDistributionChart = renderChart(
        recsysAuthorDistributionChart,
        'recsysAuthorDistributionChart',
        panel.post_distribution || null
      );
    } else {
      if (recsysAuthorReachChart) {
        recsysAuthorReachChart.destroy();
        recsysAuthorReachChart = null;
      }
      if (recsysAuthorDistributionChart) {
        recsysAuthorDistributionChart.destroy();
        recsysAuthorDistributionChart = null;
      }
      if (recsysAuthorReceiverDiversityChart) {
        recsysAuthorReceiverDiversityChart.destroy();
        recsysAuthorReceiverDiversityChart = null;
      }
    }
  }

  function renderHeatmapChart(instance, canvasId, definition) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !definition) return instance;
    if (instance) instance.destroy();

    var rowLabels = definition.row_labels || [];
    var colLabels = definition.labels || [];
    var cells = definition.cells || [];
    var options = definition.options || {};
    var colorStart = options.colorStart || [239, 246, 255];
    var colorEnd = options.colorEnd || [37, 99, 235];
    var yAxisWidth = Math.min(260, Math.max(132, rowLabels.reduce(function (max, label) {
      return Math.max(max, String(label || '').length);
    }, 0) * 7.2));

    return new Chart(canvas, {
      type: 'scatter',
      data: {
        datasets: [{
          label: definition.title || '',
          data: cells.map(function (cell) {
            return {
              x: Number(cell.x),
              y: Number(cell.y),
              actual: cell.actual,
              percent: cell.percent,
              topic_label: cell.topic_label,
              time_label: cell.time_label,
              intensity: cell.intensity
            };
          }),
          pointStyle: 'rect',
          pointRadius: 0.01,
          pointHoverRadius: 0.01,
          pointHitRadius: function (context) {
            var chart = context.chart;
            var chartArea = chart.chartArea;
            if (!chartArea) return 8;
            var colWidth = (chartArea.right - chartArea.left) / Math.max(colLabels.length, 1);
            var rowHeight = (chartArea.bottom - chartArea.top) / Math.max(rowLabels.length, 1);
            return Math.max(6, Math.min(colWidth, rowHeight) / 2);
          },
          pointBackgroundColor: function (context) {
            var raw = context.raw || {};
            return mixHeatColor(colorStart, colorEnd, raw.intensity || 0.08);
          },
          pointBorderColor: 'rgba(255,255,255,0)',
          pointBorderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 180 },
        plugins: {
          legend: { display: false },
          ysHeatmapCellPlugin: {
            enabled: true,
            rowCount: rowLabels.length,
            colCount: colLabels.length,
            getBackgroundColor: function (raw) {
              return mixHeatColor(colorStart, colorEnd, raw.intensity || 0.08);
            }
          },
          tooltip: {
            callbacks: {
              title: function (items) {
                var raw = (items[0] || {}).raw || {};
                return raw.topic_label + ' · ' + raw.time_label;
              },
              label: function (context) {
                var raw = context.raw || {};
                if (options.tooltipMode === 'reach') {
                  return 'Reached: ' + String(raw.actual || 0) + ' agents (' + Number(raw.percent || 0).toFixed(2) + '%)';
                }
                return 'Volume: ' + String(raw.actual || 0);
              }
            }
          }
        },
        scales: {
          x: {
            type: 'linear',
            min: -0.5,
            max: Math.max(colLabels.length - 0.5, 0.5),
            afterBuildTicks: function (scale) {
              scale.ticks = colLabels.map(function (_, index) {
                return { value: index };
              });
            },
            ticks: {
              callback: function (value) {
                var index = Math.round(Number(value));
                return Math.abs(Number(value) - index) < 0.001 && colLabels[index] ? colLabels[index] : '';
              },
              maxRotation: 0,
              autoSkip: true
            },
            grid: { display: false }
          },
          y: {
            type: 'linear',
            reverse: true,
            min: -0.5,
            max: Math.max(rowLabels.length - 0.5, 0.5),
            afterBuildTicks: function (scale) {
              scale.ticks = rowLabels.map(function (_, index) {
                return { value: index };
              });
            },
            afterFit: function (scale) {
              scale.width = yAxisWidth;
            },
            ticks: {
              autoSkip: false,
              font: {
                size: rowLabels.length > 16 ? 10 : 11
              },
              padding: 10,
              callback: function (value) {
                var index = Math.round(Number(value));
                return Math.abs(Number(value) - index) < 0.001 && rowLabels[index] ? rowLabels[index] : '';
              }
            },
            grid: { display: false }
          }
        }
      }
    });
  }

  function renderEgoNetwork(egoData) {
    var canvas = document.getElementById('annotationEgoNetworkChart');
    if (!canvas || !egoData) return egoNetworkChart;
    if (egoNetworkChart) egoNetworkChart.destroy();

    var nodes = egoData.nodes || [];
    var nodeLookup = {};
    nodes.forEach(function (node) { nodeLookup[node.id] = node; });
    var others = nodes.filter(function (node) { return !node.is_ego; });
    var ego = nodes.filter(function (node) { return node.is_ego; });
    var xValues = nodes.map(function (node) { return Number(node.x || 0); });
    var yValues = nodes.map(function (node) { return Number(node.y || 0); });
    var xMin = xValues.length ? Math.min.apply(null, xValues) - 0.4 : -1;
    var xMax = xValues.length ? Math.max.apply(null, xValues) + 0.4 : 1;
    var yMin = yValues.length ? Math.min.apply(null, yValues) - 0.4 : -1;
    var yMax = yValues.length ? Math.max.apply(null, yValues) + 0.4 : 1;

    egoNetworkChart = new Chart(canvas.getContext('2d'), {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Neighbors',
            data: others.map(function (node) {
              return {
                id: node.id,
                x: Number(node.x || 0),
                y: Number(node.y || 0),
                label: node.label,
                isActive: !!node.is_active,
                isEgo: false
              };
            }),
            backgroundColor: others.map(function (node) {
              return node.is_active ? 'rgba(59, 130, 246, 0.88)' : 'rgba(203, 213, 225, 0.9)';
            }),
            borderColor: others.map(function (node) {
              return node.is_active ? 'rgba(29, 78, 216, 1)' : 'rgba(100, 116, 139, 0.78)';
            }),
            pointBorderWidth: others.map(function (node) { return node.is_active ? 2 : 1.4; }),
            pointRadius: others.map(function (node) { return node.is_active ? 7 : 5.5; }),
            pointHoverRadius: 8
          },
          {
            label: 'Selected Agent',
            data: ego.map(function (node) {
              return {
                id: node.id,
                x: Number(node.x || 0),
                y: Number(node.y || 0),
                label: node.label,
                isActive: true,
                isEgo: true
              };
            }),
            backgroundColor: 'rgba(239, 68, 68, 0.94)',
            borderColor: 'rgba(153, 27, 27, 1)',
            pointBorderWidth: 3,
            pointRadius: 10.5,
            pointHoverRadius: 11.5
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 0 },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (context) {
                var raw = context.raw || {};
                if (raw.isEgo) return raw.label + ' (selected agent)';
                return raw.label + (raw.isActive ? ' (active alter)' : ' (inactive alter)');
              }
            }
          },
          ysEgoEdgePlugin: {
            edges: egoData.edges || [],
            nodeLookup: nodeLookup
          },
          ysEgoLabelPlugin: {
            nodes: nodes,
            maxVisibleLabels: 18
          }
        },
        scales: {
          x: { display: false, min: xMin, max: xMax },
          y: { display: false, min: yMin, max: yMax }
        }
      }
    });
    return egoNetworkChart;
  }

  function renderStats(stats) {
    (stats || []).forEach(function (stat) {
      var target = document.getElementById('annotation-stat-' + stat.key);
      if (target) target.textContent = stat.value;
    });
  }

  function renderSummary(summary) {
    var title = document.getElementById('annotation-summary-title');
    var head = document.getElementById('annotation-summary-head');
    var body = document.getElementById('annotation-summary-body');
    var empty = document.getElementById('annotation-summary-empty');
    if (title) title.textContent = summary.title || '';
    if (head) {
      head.innerHTML = (summary.columns || []).map(function (column) {
        return '<th>' + column + '</th>';
      }).join('');
    }
    if (body) {
      body.innerHTML = (summary.rows || []).map(function (row) {
        return '<tr>' + row.map(function (cell) {
          return '<td>' + String(cell == null ? '' : cell) + '</td>';
        }).join('') + '</tr>';
      }).join('');
    }
    if (empty) {
      empty.style.display = (summary.rows && summary.rows.length) ? 'none' : '';
      var bodyNode = empty.querySelector('.message-body');
      if (bodyNode) bodyNode.textContent = summary.empty_message || '';
    }
  }

  function updateModeratorTargetSection(targets) {
    var panel = document.getElementById('tox-moderator-target-panel');
    if (!panel) return;

    var options = targets.options || [];
    var select = document.getElementById('tox-moderator-target-select');
    var emptyState = document.getElementById('tox-moderator-empty-state');
    var chartColumn = document.getElementById('tox-moderator-chart-column');
    var eventsColumn = document.getElementById('tox-moderator-events-column');
    var deployed = document.getElementById('tox-moderator-deployed');
    if (deployed) deployed.textContent = targets.deployed_agents || 0;
    if (!select) return;

    var hasOptions = options.length > 0;
    select.disabled = !hasOptions;
    if (emptyState) emptyState.style.display = hasOptions ? 'none' : '';
    if (chartColumn) chartColumn.style.display = hasOptions ? '' : 'none';
    if (eventsColumn) eventsColumn.style.display = hasOptions ? '' : 'none';

    var currentSelection = targets.selected_uid || '';
    select.innerHTML = options.map(function (option) {
      var selected = option.uid === currentSelection ? ' selected' : '';
      return '<option value="' + option.uid + '"' + selected + '>' +
        option.username + ' (' + option.moderation_count + ' interventions)</option>';
    }).join('');

    var targetName = document.getElementById('tox-moderator-target-name');
    var interactionCount = document.getElementById('tox-moderator-interaction-count');
    var moderatorNames = document.getElementById('tox-moderator-agent-names');
    if (targetName) targetName.textContent = hasOptions ? (targets.selected_username || '—') : '—';
    if (interactionCount) interactionCount.textContent = hasOptions ? (targets.moderation_count || 0) : 0;
    if (moderatorNames) moderatorNames.textContent = hasOptions ? ((targets.moderator_usernames || []).join(', ') || '—') : '—';

    var eventTable = document.getElementById('tox-moderator-events-body');
    if (eventTable) {
      var events = targets.interaction_events || [];
      eventTable.innerHTML = events.length
        ? events.map(function (event) {
            return '<tr>' +
              '<td>Day ' + event.day + ', Hour ' + event.hour + '</td>' +
              '<td>' + String(event.moderation_type || '').replace(/_/g, ' ').replace(/\b\w/g, function (ch) { return ch.toUpperCase(); }) + '</td>' +
              '<td>' + event.moderation_count + '</td>' +
              '<td>' + (((event.moderator_usernames || []).join(', ')) || '—') + '</td>' +
              '</tr>';
          }).join('')
        : '<tr><td colspan="4" class="has-text-centered has-text-grey">No moderation actions recorded.</td></tr>';
    }

    if (hasOptions) {
      renderModeratorTargetChart(targets.trend_data || { timestamps: [], timestamp_mapping: {}, datasets: [] });
    } else if (moderatorTargetChart) {
      moderatorTargetChart.destroy();
      moderatorTargetChart = null;
    }
  }

  function renderTexts(analytics) {
    var mappings = [
      ['annotation-distribution-title', analytics.distribution.title],
      ['annotation-distribution-description', analytics.distribution.description],
      ['annotation-trend-title', analytics.trend.title],
      ['annotation-trend-description', analytics.trend.description],
      ['annotation-secondary-title', analytics.secondary.title],
      ['annotation-secondary-description', analytics.secondary.description]
    ];
    mappings.forEach(function (pair) {
      var node = document.getElementById(pair[0]);
      if (node) node.textContent = pair[1] || '';
    });
  }

  function computeTopicHeatmapHeight(rowCount) {
    return Math.max(240, Math.min(680, 80 + (Number(rowCount || 0) * 34)));
  }

  function syncTopicHeatmapContainers(analytics) {
    if (config.pageKey !== 'topic' && config.pageKey !== 'hashtag') return;
    var rowCount = Math.max(
      (((analytics || {}).trend || {}).row_labels || []).length,
      (((analytics || {}).secondary || {}).row_labels || []).length,
      1
    );
    var targetHeight = computeTopicHeatmapHeight(rowCount);
    ['annotationTrendChartContainer', 'annotationSecondaryChartContainer'].forEach(function (id) {
      var node = document.getElementById(id);
      if (!node || node.classList.contains('is-fullscreen')) return;
      node.style.height = targetHeight + 'px';
      node.style.minHeight = targetHeight + 'px';
    });
  }

  function renderAnalytics(analytics) {
    syncTopicHeatmapContainers(analytics);
    renderTexts(analytics);
    renderStats(analytics.stats || []);
    distributionChart = analytics.distribution && analytics.distribution.type === 'heatmap'
      ? renderHeatmapChart(distributionChart, 'annotationDistributionChart', analytics.distribution)
      : renderChart(distributionChart, 'annotationDistributionChart', analytics.distribution);
    trendChart = analytics.trend && analytics.trend.type === 'heatmap'
      ? renderHeatmapChart(trendChart, 'annotationTrendChart', analytics.trend)
      : renderChart(trendChart, 'annotationTrendChart', analytics.trend);
    secondaryChart = analytics.secondary && analytics.secondary.type === 'heatmap'
      ? renderHeatmapChart(secondaryChart, 'annotationSecondaryChart', analytics.secondary)
      : renderChart(secondaryChart, 'annotationSecondaryChart', analytics.secondary);
    if (config.pageKey === 'network') {
      componentShareChart = renderComponentShareChart(analytics.component_share || null);
      networkStructureChart = renderNetworkStructureChart(analytics.network_structure || null);
      renderEgoNetwork(analytics.ego_network || null);
      var egoSelect = document.getElementById('annotation-network-ego-select');
      if (egoSelect && analytics.ego_network) {
        var selected = analytics.ego_network.selected_uid || '';
        var placeholderHtml = '<option value=""' + (selected ? '' : ' selected') + '>Choose an account…</option>';
        egoSelect.innerHTML = placeholderHtml + (analytics.ego_network.options || []).map(function (option) {
          var sel = option.uid === selected ? ' selected' : '';
          return '<option value="' + option.uid + '"' + sel + '>' +
            option.username + ' (deg ' + option.degree + ')' +
            '</option>';
        }).join('');
      }
      var componentTitle = document.getElementById('annotation-component-title');
      var componentDescription = document.getElementById('annotation-component-description');
      if (componentTitle && analytics.component_share) componentTitle.textContent = analytics.component_share.title || '';
      if (componentDescription && analytics.component_share) componentDescription.textContent = analytics.component_share.description || '';
      var structureTitle = document.getElementById('annotation-network-structure-title');
      var structureDescription = document.getElementById('annotation-network-structure-description');
      if (structureTitle && analytics.network_structure) structureTitle.textContent = analytics.network_structure.title || '';
      if (structureDescription && analytics.network_structure) structureDescription.textContent = analytics.network_structure.description || '';
      var egoTitle = document.getElementById('annotation-ego-title');
      var egoDescription = document.getElementById('annotation-ego-description');
      if (egoTitle && analytics.ego_network) egoTitle.textContent = analytics.ego_network.title || '';
      if (egoDescription && analytics.ego_network) egoDescription.textContent = analytics.ego_network.description || '';
    }
    if (config.pageKey === 'topic' || config.pageKey === 'hashtag') {
      topicLifecycleChart = renderTopicLifecycleChart(analytics.topic_lifecycle || null);
      var topicLifecycleTitle = document.getElementById('annotation-topic-lifecycle-title');
      var topicLifecycleDescription = document.getElementById('annotation-topic-lifecycle-description');
      if (topicLifecycleTitle && analytics.topic_lifecycle) topicLifecycleTitle.textContent = analytics.topic_lifecycle.title || '';
      if (topicLifecycleDescription && analytics.topic_lifecycle) topicLifecycleDescription.textContent = analytics.topic_lifecycle.description || '';
      var topicSelect = document.getElementById('annotation-topic-select');
      if (topicSelect && Array.isArray(analytics.selector_options || analytics.topic_options)) {
        var selectedMap = {};
        (analytics.selected_ids || analytics.selected_topic_ids || []).forEach(function (topicId) {
          selectedMap[String(topicId)] = true;
        });
        (analytics.selector_options || analytics.topic_options || []).forEach(function (option) {
          if (option.topic_id != null && option.value == null) {
            option.value = option.topic_id;
            option.label = String(option.topic_name) + ' (' + String(option.total_volume || 0) + ')';
          }
        });
        topicSelect.innerHTML = (analytics.selector_options || analytics.topic_options).map(function (option) {
          var selected = selectedMap[String(option.value)] ? ' selected' : '';
          return '<option value="' + String(option.value) + '"' + selected + '>' + String(option.label) + '</option>';
        }).join('');
      }
      var topicTrendModeSelect = document.getElementById('annotation-topic-trend-mode-select');
      if (topicTrendModeSelect && analytics.trend_mode) {
        topicTrendModeSelect.value = analytics.trend_mode;
      }
    }
    if (config.pageKey === 'toxicity' && analytics.moderator_targets) {
      updateModeratorTargetSection(analytics.moderator_targets);
    }
    if (config.pageKey === 'recsys' && analytics.recsys_author) {
      updateRecsysAuthorSection(analytics.recsys_author);
    }
    renderSummary(analytics.summary || { columns: [], rows: [], empty_message: '' });
    resizeAllCharts();
  }

  function setLoading(isLoading) {
    var overlay = document.getElementById('annotation-loading-overlay');
    if (!overlay) return;
    overlay.style.display = isLoading ? 'flex' : 'none';
  }

  function updateTimeLabels() {
    var day = document.getElementById('annotation-stat-current_day');
    var hour = document.getElementById('annotation-stat-current_hour');
    if (day) day.textContent = 'Day ' + state.currentDay;
    if (hour) hour.textContent = 'Hour ' + state.currentHour;
  }

  function updateSpeedDisplay() {
    var node = document.getElementById('annotation-speed-display');
    if (node) node.textContent = state.speedMultipliers[state.speedIndex] + 'x';
  }

  function getGranularityStep() {
    if (state.currentGranularity === 'daily') return 24;
    if (state.currentGranularity === 'weekly') return 168;
    return 1;
  }

  function snapToGranularity(value) {
    var numeric = Number(value || 0);
    var step = getGranularityStep();
    if (step === 1) return numeric;
    var day = Math.floor(numeric / 24);
    if (state.currentGranularity === 'daily') return day * 24;
    return Math.floor(day / 7) * 168;
  }

  function updateGranularityButtons() {
    document.querySelectorAll('.annotation-granularity-button').forEach(function (button) {
      button.classList.toggle('active', button.dataset.granularity === state.currentGranularity);
    });
  }

  function fetchAnnotationAnalytics(day, hour) {
    var thresholdInput = document.getElementById('annotation-toxicity-threshold');
    var threshold = thresholdInput ? Number(thresholdInput.value || config.threshold || 0.1) : null;
    var egoSelect = document.getElementById('annotation-network-ego-select');
    var networkTypeSelect = document.getElementById('annotation-network-type-select');
    var granularitySelect = document.getElementById('annotation-network-granularity-select');
    var topicSelect = document.getElementById('annotation-topic-select');
    var topicTrendModeSelect = document.getElementById('annotation-topic-trend-mode-select');
    var moderatorTargetSelect = document.getElementById('tox-moderator-target-select');
    var recsysAuthorSelect = document.getElementById('annotation-recsys-author-select');
    setLoading(true);
    var url = config.dataUrl + '?day=' + day + '&hour=' + hour;
    if (thresholdInput) {
      url += '&threshold=' + encodeURIComponent(String(threshold));
    }
    if (config.pageKey === 'network' && networkTypeSelect && networkTypeSelect.value) {
      url += '&network_type=' + encodeURIComponent(String(networkTypeSelect.value));
    }
    if (config.pageKey === 'network' && granularitySelect && granularitySelect.value) {
      url += '&granularity=' + encodeURIComponent(String(granularitySelect.value));
    }
    if (config.pageKey === 'network' && egoSelect && egoSelect.value) {
      url += '&target_uid=' + encodeURIComponent(String(egoSelect.value));
    }
    if ((config.pageKey === 'topic' || config.pageKey === 'hashtag') && topicSelect) {
      Array.prototype.slice.call(topicSelect.selectedOptions || []).forEach(function (option) {
        url += '&topic_ids=' + encodeURIComponent(String(option.value));
      });
    }
    if ((config.pageKey === 'topic' || config.pageKey === 'hashtag') && topicTrendModeSelect && topicTrendModeSelect.value) {
      url += '&trend_mode=' + encodeURIComponent(String(topicTrendModeSelect.value));
    }
    if (config.pageKey === 'toxicity' && moderatorTargetSelect && moderatorTargetSelect.value) {
      url += '&target_uid=' + encodeURIComponent(String(moderatorTargetSelect.value));
    }
    if (config.pageKey === 'recsys' && recsysAuthorSelect && recsysAuthorSelect.value) {
      url += '&target_uid=' + encodeURIComponent(String(recsysAuthorSelect.value));
    }
    fetch(url)
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (payload.error) throw new Error(payload.error);
        state.currentDay = Number(payload.filter_day || day);
        state.currentHour = Number(payload.filter_hour || hour);
        state.currentAnalytics = payload.analytics || {};
        if (thresholdInput && typeof payload.threshold === 'number') {
          thresholdInput.value = payload.threshold.toFixed(2);
        }
        renderAnalytics(state.currentAnalytics);
        updateTimeLabels();
      })
      .catch(function (error) {
        console.error('Failed to fetch annotation analytics:', error);
      })
      .finally(function () {
        setLoading(false);
      });
  }

  function sliderValueToTime(value) {
    var numeric = snapToGranularity(value);
    return {
      day: Math.floor(numeric / 24),
      hour: numeric % 24
    };
  }

  function stepPlayback() {
    var slider = document.getElementById('annotation-time-slider');
    if (!slider) return;
    var step = getGranularityStep() * state.speedMultipliers[state.speedIndex];
    var nextValue = Math.min(Number(slider.value) + step, Number(slider.max));
    nextValue = snapToGranularity(nextValue);
    slider.value = String(nextValue);
    var time = sliderValueToTime(nextValue);
    fetchAnnotationAnalytics(time.day, time.hour);
    if (nextValue >= Number(slider.max)) {
      togglePlayback(false);
    }
  }

  function togglePlayback(forceState) {
    var playButton = document.getElementById('annotation-play-button');
    state.playing = typeof forceState === 'boolean' ? forceState : !state.playing;
    if (state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
    if (state.playing) {
      state.timer = setInterval(stepPlayback, 1000);
    }
    if (playButton) {
      playButton.innerHTML = state.playing
        ? '<i class="mdi mdi-pause"></i>'
        : '<i class="mdi mdi-play"></i>';
    }
  }

  function bindControls() {
    var slider = document.getElementById('annotation-time-slider');
    if (slider) {
      slider.addEventListener('input', function () {
        var snappedValue = snapToGranularity(slider.value);
        slider.value = String(snappedValue);
        var time = sliderValueToTime(snappedValue);
        fetchAnnotationAnalytics(time.day, time.hour);
      });
    }

    var playButton = document.getElementById('annotation-play-button');
    if (playButton) {
      playButton.addEventListener('click', function () { togglePlayback(); });
    }

    var speedDown = document.getElementById('annotation-speed-down');
    if (speedDown) {
      speedDown.addEventListener('click', function () {
        state.speedIndex = Math.max(0, state.speedIndex - 1);
        updateSpeedDisplay();
      });
    }

    var speedUp = document.getElementById('annotation-speed-up');
    if (speedUp) {
      speedUp.addEventListener('click', function () {
        state.speedIndex = Math.min(state.speedMultipliers.length - 1, state.speedIndex + 1);
        updateSpeedDisplay();
      });
    }

    var thresholdInput = document.getElementById('annotation-toxicity-threshold');
    if (thresholdInput) {
      thresholdInput.addEventListener('change', function () {
        var value = Number(thresholdInput.value || config.threshold || 0.1);
        if (Number.isNaN(value)) value = 0.1;
        value = Math.max(0, Math.min(1, Math.round(value * 100) / 100));
        thresholdInput.value = value.toFixed(2);
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var networkTypeSelect = document.getElementById('annotation-network-type-select');
    if (networkTypeSelect) {
      networkTypeSelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var granularitySelect = document.getElementById('annotation-network-granularity-select');
    if (granularitySelect) {
      granularitySelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var egoSelect = document.getElementById('annotation-network-ego-select');
    if (egoSelect) {
      egoSelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var topicSelect = document.getElementById('annotation-topic-select');
    if (topicSelect) {
      topicSelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var topicTrendModeSelect = document.getElementById('annotation-topic-trend-mode-select');
    if (topicTrendModeSelect) {
      topicTrendModeSelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var moderatorTargetSelect = document.getElementById('tox-moderator-target-select');
    if (moderatorTargetSelect) {
      moderatorTargetSelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    var recsysAuthorSelect = document.getElementById('annotation-recsys-author-select');
    if (recsysAuthorSelect) {
      recsysAuthorSelect.addEventListener('change', function () {
        fetchAnnotationAnalytics(state.currentDay, state.currentHour);
      });
    }

    document.querySelectorAll('.annotation-granularity-button').forEach(function (button) {
      button.addEventListener('click', function () {
        state.currentGranularity = button.dataset.granularity || 'hourly';
        updateGranularityButtons();
        var slider = document.getElementById('annotation-time-slider');
        if (slider) {
          var snappedValue = snapToGranularity(slider.value);
          slider.value = String(snappedValue);
          var time = sliderValueToTime(snappedValue);
          fetchAnnotationAnalytics(time.day, time.hour);
        }
      });
    });

  }

  bindControls();
  updateSpeedDisplay();
  updateGranularityButtons();
  renderAnalytics(state.currentAnalytics);
  window.addEventListener('resize', resizeAllCharts);
})();
