(function () {
  var config = window.YS_DATA_ANNOTATION_ANALYTICS || {};
  if (!config.expId) return;

  var state = {
    currentDay: Number(config.filterDay || 1),
    currentHour: Number(config.filterHour || 1),
    maxTick: Number(config.maxTick || 24),
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

  var egoEdgePlugin = {
    id: 'ysEgoEdgePlugin',
    beforeDatasetsDraw: function (chart, args, pluginOptions) {
      if (!pluginOptions || !pluginOptions.edges || !pluginOptions.edges.length) return;
      var xScale = chart.scales.x;
      var yScale = chart.scales.y;
      if (!xScale || !yScale) return;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = pluginOptions.color || 'rgba(148, 163, 184, 0.65)';
      ctx.lineWidth = pluginOptions.lineWidth || 1.2;
      (pluginOptions.edges || []).forEach(function (edge) {
        ctx.beginPath();
        ctx.moveTo(xScale.getPixelForValue(edge.x1), yScale.getPixelForValue(edge.y1));
        ctx.lineTo(xScale.getPixelForValue(edge.x2), yScale.getPixelForValue(edge.y2));
        ctx.stroke();
      });
      ctx.restore();
    }
  };
  if (typeof Chart !== 'undefined') {
    try { Chart.register(egoEdgePlugin); } catch (e) {}
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

  function renderEgoNetwork(egoData) {
    var canvas = document.getElementById('annotationEgoNetworkChart');
    if (!canvas || !egoData) return egoNetworkChart;
    if (egoNetworkChart) egoNetworkChart.destroy();

    var nodes = egoData.nodes || [];
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
                x: Number(node.x || 0),
                y: Number(node.y || 0),
                label: node.label,
                isActive: !!node.is_active
              };
            }),
            backgroundColor: others.map(function (node) {
              return node.is_active ? 'rgba(59, 130, 246, 0.95)' : 'rgba(148, 163, 184, 0.55)';
            }),
            borderColor: others.map(function (node) {
              return node.is_active ? 'rgba(37, 99, 235, 1)' : 'rgba(100, 116, 139, 0.9)';
            }),
            pointRadius: others.map(function (node) { return node.is_active ? 6 : 4; }),
            pointHoverRadius: 7
          },
          {
            label: 'Selected Agent',
            data: ego.map(function (node) {
              return {
                x: Number(node.x || 0),
                y: Number(node.y || 0),
                label: node.label,
                isActive: true
              };
            }),
            backgroundColor: 'rgba(239, 68, 68, 0.95)',
            borderColor: 'rgba(185, 28, 28, 1)',
            pointRadius: 8,
            pointHoverRadius: 9
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
              label: function (context) {
                var raw = context.raw || {};
                return raw.label + (context.dataset.label === 'Neighbors' ? (raw.isActive ? ' (active)' : ' (inactive)') : '');
              }
            }
          },
          ysEgoEdgePlugin: {
            edges: egoData.edges || []
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

  function renderAnalytics(analytics) {
    renderTexts(analytics);
    renderStats(analytics.stats || []);
    distributionChart = renderChart(distributionChart, 'annotationDistributionChart', analytics.distribution);
    trendChart = renderChart(trendChart, 'annotationTrendChart', analytics.trend);
    secondaryChart = renderChart(secondaryChart, 'annotationSecondaryChart', analytics.secondary);
    if (config.pageKey === 'network') {
      componentShareChart = renderComponentShareChart(analytics.component_share || null);
      networkStructureChart = renderNetworkStructureChart(analytics.network_structure || null);
      renderEgoNetwork(analytics.ego_network || null);
      var egoSelect = document.getElementById('annotation-network-ego-select');
      if (egoSelect && analytics.ego_network) {
        var selected = analytics.ego_network.selected_uid || '';
        egoSelect.innerHTML = (analytics.ego_network.options || []).map(function (option) {
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
    if (config.pageKey === 'topic') {
      topicLifecycleChart = renderTopicLifecycleChart(analytics.topic_lifecycle || null);
      var topicLifecycleTitle = document.getElementById('annotation-topic-lifecycle-title');
      var topicLifecycleDescription = document.getElementById('annotation-topic-lifecycle-description');
      if (topicLifecycleTitle && analytics.topic_lifecycle) topicLifecycleTitle.textContent = analytics.topic_lifecycle.title || '';
      if (topicLifecycleDescription && analytics.topic_lifecycle) topicLifecycleDescription.textContent = analytics.topic_lifecycle.description || '';
      var topicSelect = document.getElementById('annotation-topic-select');
      if (topicSelect && Array.isArray(analytics.topic_options)) {
        var selectedMap = {};
        (analytics.selected_topic_ids || []).forEach(function (topicId) {
          selectedMap[String(topicId)] = true;
        });
        topicSelect.innerHTML = analytics.topic_options.map(function (option) {
          var selected = selectedMap[String(option.topic_id)] ? ' selected' : '';
          var label = String(option.topic_name) + ' (' + String(option.total_volume || 0) + ')';
          return '<option value="' + String(option.topic_id) + '"' + selected + '>' + label + '</option>';
        }).join('');
      }
      var topicTrendModeSelect = document.getElementById('annotation-topic-trend-mode-select');
      if (topicTrendModeSelect && analytics.trend_mode) {
        topicTrendModeSelect.value = analytics.trend_mode;
      }
    }
    renderSummary(analytics.summary || { columns: [], rows: [], empty_message: '' });
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
    if (config.pageKey === 'topic' && topicSelect) {
      Array.prototype.slice.call(topicSelect.selectedOptions || []).forEach(function (option) {
        url += '&topic_ids=' + encodeURIComponent(String(option.value));
      });
    }
    if (config.pageKey === 'topic' && topicTrendModeSelect && topicTrendModeSelect.value) {
      url += '&trend_mode=' + encodeURIComponent(String(topicTrendModeSelect.value));
    }
    fetch(url)
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (payload.error) throw new Error(payload.error);
        state.currentDay = Number(payload.filter_day || day);
        state.currentHour = Number(payload.filter_hour || hour);
        if (thresholdInput && typeof payload.threshold === 'number') {
          thresholdInput.value = payload.threshold.toFixed(2);
        }
        renderAnalytics(payload.analytics || {});
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
  renderAnalytics(config.analytics || {});
})();
