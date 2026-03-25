var AdminOpinion = (function() {
  const bindById = (id, eventName, handler) => {
      const element = document.getElementById(id);
      if (element) {
          element.addEventListener(eventName, handler);
      }
      return element;
  };


    // ── Opinion Configuration ──────────────────────────────────────────────

    var _selectedDimensions = [];

    function formatDistributionParamValue(value) {
        if (Array.isArray(value)) return value.join(', ');
        if (value && typeof value === 'object') return JSON.stringify(value);
        return String(value);
    }

    function buildDistributionParamsMarkup(parameters) {
        var entries = Object.entries(parameters || {});
        if (!entries.length) {
            return '<div class="dist-note">No fixed parameters defined for this distribution.</div>';
        }
        return '<div class="dist-meta-label">Fixed Parameters</div>' +
            '<div class="dist-params">' +
            entries.map(function(e) {
                return '<span class="dist-param"><span class="dist-param-key">' + e[0] + ':</span><span>' + formatDistributionParamValue(e[1]) + '</span></span>';
            }).join('') +
            '</div>';
    }

    function buildDistributionNote(type) {
        var supported = new Set([
            'uniform', 'normal', 'beta', 'exponential', 'gamma',
            'lognormal', 'bimodal', 'polarized'
        ]);
        if (supported.has(type)) {
            return '';
        }
        return '<div class="dist-note is-custom">Custom distribution type <strong>' + type + '</strong>. Sampling is delegated to the backend implementation, so newly added DB-driven distributions remain available without template changes.</div>';
    }

    function clampProbability(value) {
        if (!isFinite(value) || isNaN(value)) return 0;
        return Math.max(0, value);
    }

    function gaussianPdf(x, mu, sigma) {
        if (!sigma || sigma <= 0) sigma = 0.2;
        var z = (x - mu) / sigma;
        return Math.exp(-0.5 * z * z);
    }

    function betaPdfLike(x, a, b) {
        a = Number(a);
        b = Number(b);
        if (!isFinite(a) || a <= 0) a = 2;
        if (!isFinite(b) || b <= 0) b = 5;
        var epsilon = 1e-4;
        var safeX = Math.min(1 - epsilon, Math.max(epsilon, x));
        return Math.pow(safeX, a - 1) * Math.pow(1 - safeX, b - 1);
    }

    function exponentialPdfLike(x, scale) {
        scale = Number(scale);
        if (!isFinite(scale) || scale <= 0) scale = 1;
        return Math.exp(-x / scale);
    }

    function gammaPdfLike(x, shape, scale) {
        shape = Number(shape);
        scale = Number(scale);
        if (!isFinite(shape) || shape <= 0) shape = 2;
        if (!isFinite(scale) || scale <= 0) scale = 1;
        var scaledX = Math.max(x, 1e-4);
        return Math.pow(scaledX, shape - 1) * Math.exp(-scaledX / scale);
    }

    function lognormalPdfLike(x, mean, sigma) {
        mean = Number(mean);
        sigma = Number(sigma);
        if (!isFinite(mean)) mean = 0;
        if (!isFinite(sigma) || sigma <= 0) sigma = 1;
        var safeX = Math.max(x, 1e-4);
        var exponent = -Math.pow(Math.log(safeX) - mean, 2) / (2 * sigma * sigma);
        return Math.exp(exponent) / safeX;
    }

    function densityAt(x, type, params, index, totalSteps) {
        var y = 0;
        if (type === 'uniform') {
            y = 1;
        } else if (type === 'normal') {
            y = gaussianPdf(x, Number(params.loc || 0.5), Number(params.scale || 0.2));
        } else if (type === 'beta') {
            y = betaPdfLike(x, params.a, params.b);
        } else if (type === 'exponential') {
            y = exponentialPdfLike(x, params.scale);
        } else if (type === 'gamma') {
            y = gammaPdfLike(x, params.shape, params.scale);
        } else if (type === 'lognormal') {
            y = lognormalPdfLike(x, params.mean, params.sigma);
        } else if (type === 'bimodal') {
            y =
                gaussianPdf(x, Number(params.peak1 || 0.2), Number(params.sigma || 0.15)) +
                gaussianPdf(x, Number(params.peak2 || 0.8), Number(params.sigma || 0.15));
        } else if (type === 'polarized') {
            y = (index === 0 || index === totalSteps - 1) ? 1 : 0;
        } else {
            y = 1;
        }
        return clampProbability(y);
    }

    function buildPreviewSeries(dist, bins, labels) {
        var type = (dist.type || 'custom').toLowerCase();
        var params = dist.parameters || {};
        var resolvedBins = Array.isArray(bins) && bins.length >= 2
            ? bins
            : [0.0, 0.25, 0.5, 0.75, 1.0];
        var resolvedLabels = Array.isArray(labels) && labels.length === resolvedBins.length - 1
            ? labels
            : resolvedBins.slice(0, -1).map(function(value, idx) {
                var next = resolvedBins[idx + 1];
                return value + '–' + next;
            });
        var data = [];

        for (var i = 0; i < resolvedBins.length - 1; i++) {
            var start = Number(resolvedBins[i]);
            var end = Number(resolvedBins[i + 1]);
            var midpoint = (start + end) / 2;
            var width = Math.max(end - start, 0.0001);
            data.push(
                densityAt(midpoint, type, params, i, resolvedBins.length - 1) * width
            );
        }

        var maxValue = Math.max.apply(null, data);
        if (maxValue > 0) {
            data = data.map(function(value) { return value / maxValue; });
        }

        return { labels: resolvedLabels, data: data };
    }

    function createDistributionChart(canvas, dist, index) {
        if (!canvas || typeof Chart === 'undefined') return;

        var config = window.YS_DATA_OPINION || {};
        var palette = [
            ['rgba(168, 85, 247, 0.72)', 'rgba(168, 85, 247, 1)'],
            ['rgba(236, 72, 153, 0.72)', 'rgba(236, 72, 153, 1)'],
            ['rgba(34, 197, 94, 0.72)', 'rgba(34, 197, 94, 1)'],
            ['rgba(59, 130, 246, 0.72)', 'rgba(59, 130, 246, 1)'],
            ['rgba(251, 146, 60, 0.72)', 'rgba(251, 146, 60, 1)'],
            ['rgba(239, 68, 68, 0.72)', 'rgba(239, 68, 68, 1)']
        ];
        var colors = palette[index % palette.length];
        var preview = buildPreviewSeries(dist, config.bins, config.labels);

        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: preview.labels,
                datasets: [{
                    data: preview.data,
                    backgroundColor: colors[0],
                    borderColor: colors[1],
                    borderWidth: 1,
                    borderRadius: 2,
                    barPercentage: 1.0,
                    categoryPercentage: 1.0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                layout: {
                    padding: {
                        bottom: 8
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                scales: {
                    y: {
                        display: false,
                        beginAtZero: true,
                        suggestedMax: 1
                    },
                    x: {
                        display: true,
                        grid: { display: false },
                        ticks: {
                            autoSkip: false,
                            maxRotation: 45,
                            minRotation: 45,
                            color: '#6b7280',
                            callback: function(value, tickIndex) {
                                var label = preview.labels[tickIndex];
                                if (typeof label !== 'string') return label;
                                if (label.length <= 12) return label;
                                return label.split(/\s+/);
                            },
                            font: {
                                size: 9
                            }
                        }
                    }
                }
            }
        });
    }

    function initializeDistributionPreviews() {
        var config = window.YS_DATA_OPINION || {};
        var distributions = config.distributions || [];
        var grid = document.getElementById('distributions-grid');
        if (!grid) return;
        grid.innerHTML = '';
        distributions.forEach(function(dist, index) {
            var preview = document.createElement('div');
            preview.className = 'dist-preview';
            var distType = dist.type || 'custom';
            preview.innerHTML = '<div class="dist-header"><div class="dist-name">' + dist.name + '</div><span class="dist-type-badge">' + distType + '</span></div>' +
                '<div class="dist-chart-box" style="position: relative; height: 160px;"><canvas class="dist-chart-canvas"></canvas></div>' +
                '<div class="dist-body">' + buildDistributionParamsMarkup(dist.parameters) + buildDistributionNote(distType) + '</div>';
            grid.appendChild(preview);
            var canvas = preview.querySelector('.dist-chart-canvas');
            createDistributionChart(canvas, dist, index);
        });
    }

    function toggleDimension(tag) {
        var id = tag.getAttribute('data-id');
        if (tag.classList.contains('inactive')) {
            tag.classList.remove('inactive');
            tag.classList.add('selected');
            _selectedDimensions.push(id);
        } else {
            tag.classList.remove('selected');
            tag.classList.add('inactive');
            _selectedDimensions = _selectedDimensions.filter(function(d) { return d !== id; });
        }
        updateSegmentation();
    }

    function updateSegmentation() {
        document.getElementById('segmentation-input').value = _selectedDimensions.join(',');
        generateSegmentConfigurations();
    }

    function selectUpdateRule(button, ruleValue) {
        if (button.classList.contains('disabled')) return;
        document.querySelectorAll('.update-rule-button').forEach(function(btn) {
            btn.classList.remove('selected');
        });
        button.classList.add('selected');
        document.getElementById('update_rule_input').value = ruleValue;
        var bcParams = document.getElementById('bounded-confidence-params');
        var llmParams = document.getElementById('llm-evaluation-params');
        if (ruleValue === 'bounded_confidence') {
            bcParams.style.display = 'block';
            llmParams.style.display = 'none';
        } else if (ruleValue === 'llm_evaluation') {
            bcParams.style.display = 'none';
            llmParams.style.display = 'block';
        }
    }

    function toggleUpdateRuleOptions() {
        var selectedRule = document.getElementById('update_rule_input').value;
        var bcParams = document.getElementById('bounded-confidence-params');
        var llmParams = document.getElementById('llm-evaluation-params');
        if (selectedRule === 'bounded_confidence') {
            bcParams.style.display = 'block';
            llmParams.style.display = 'none';
        } else if (selectedRule === 'llm_evaluation') {
            bcParams.style.display = 'none';
            llmParams.style.display = 'block';
        }
    }

    function generateSegmentConfigurations() {
        var config = window.YS_DATA_OPINION || {};
        var topics = config.topics || [];
        var distributions = config.distributions || [];
        var segmentValues = config.segmentValues || {};
        var segments = generateSegments(_selectedDimensions, segmentValues);

        topics.forEach(function(topic) {
            var containerId = 'segments-topic-' + topic.id;
            var container = document.getElementById(containerId);
            if (!container) return;
            while (container.firstChild) container.removeChild(container.firstChild);

            segments.forEach(function(segment, segmentIndex) {
                var segmentDiv = document.createElement('div');
                segmentDiv.className = 'segment-config';
                var label = document.createElement('div');
                label.className = 'segment-label';
                label.textContent = segment;
                var selectWrapper = document.createElement('div');
                selectWrapper.className = 'segment-select';
                var select = document.createElement('select');
                select.className = 'input';
                select.name = 'dist_topic_' + topic.id + '_segment_' + segmentIndex;
                select.setAttribute('data-segment-name', segment);
                distributions.forEach(function(dist, idx) {
                    var option = document.createElement('option');
                    option.value = dist.name;
                    option.textContent = dist.name;
                    if (idx === 0) option.selected = true;
                    select.appendChild(option);
                });
                selectWrapper.appendChild(select);
                segmentDiv.appendChild(label);
                segmentDiv.appendChild(selectWrapper);
                container.appendChild(segmentDiv);
            });
        });
    }

    function generateSegments(dimensions, segmentValues) {
        if (!dimensions.length) return ['All Population'];
        var segments = [''];
        dimensions.forEach(function(dim) {
            var values = (segmentValues || {})[dim] || [];
            if (!values.length) return;
            var newSegments = [];
            segments.forEach(function(segment) {
                values.forEach(function(value) {
                    newSegments.push(segment ? segment + ' - ' + value : value);
                });
            });
            segments = newSegments;
        });
        return segments;
    }

    function initOpinionConfiguration() {
        initializeDistributionPreviews();

        var config = window.YS_DATA_OPINION || {};
        console.log('Topics:', config.topics);
        console.log('Segment Values:', config.segmentValues);
        console.log('Distributions:', config.distributions);

        document.querySelectorAll('.dimension-tag').forEach(function(tag) {
            tag.addEventListener('click', function() { toggleDimension(this); });
        });

        var closeBtn = document.getElementById('close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                var redirectUrl = this.getAttribute('data-redirect-url');
                if (redirectUrl) window.location.href = redirectUrl;
            });
        }

        generateSegmentConfigurations();
    }

    // ── Opinion Evolution ──────────────────────────────────────────────────

    var _evoChartInstance = null;
    var _evoGroupTrendsChartInstance = null;
    var _evoTimeseriesChartInstance = null;
    var _currentSamplePercentage = 50;
    var _currentTopicId = null;
    var _isPlaying = false;
    var _playInterval = null;
    var _loadingTimeout = null;
    var _currentGranularity = 'hourly';
    var _currentSpeedIndex = 2;
    var _baseInterval = 500;
    var _maxTimeValue = 0;
    var _minTimeValue = 25;
    var _speeds = [0.25, 0.5, 1, 2, 4, 6, 8, 10];
    var _evoChartValues = [];
    var _currentGroupTrendsData = null;
    var _currentTimeseriesData = null;

    function generateChartColors(count) {
        var colors = [], borderColors = [];
        var colorPalette = [
            { bg: 'rgba(239, 68, 68, 0.7)', border: 'rgba(239, 68, 68, 1)' },
            { bg: 'rgba(251, 146, 60, 0.7)', border: 'rgba(251, 146, 60, 1)' },
            { bg: 'rgba(250, 204, 21, 0.7)', border: 'rgba(250, 204, 21, 1)' },
            { bg: 'rgba(74, 222, 128, 0.7)', border: 'rgba(74, 222, 128, 1)' },
            { bg: 'rgba(22, 163, 74, 0.7)', border: 'rgba(22, 163, 74, 1)' }
        ];
        for (var i = 0; i < count; i++) {
            if (i < colorPalette.length) {
                colors.push(colorPalette[i].bg);
                borderColors.push(colorPalette[i].border);
            } else {
                var hue = (i * 360 / count);
                colors.push('hsla(' + hue + ', 70%, 60%, 0.7)');
                borderColors.push('hsla(' + hue + ', 70%, 60%, 1)');
            }
        }
        return { colors: colors, borderColors: borderColors };
    }

    function createGroupTrendsDatasets(groupTrendsData) {
        var colors = generateChartColors(groupTrendsData.groups.length);
        return groupTrendsData.groups.map(function(group, index) {
            return {
                label: group.name,
                data: group.data,
                borderColor: colors.borderColors[index],
                backgroundColor: colors.colors[index].replace('0.7', '0.6'),
                borderWidth: 1,
                pointRadius: 0,
                pointHoverRadius: 3,
                tension: 0.3,
                fill: true
            };
        });
    }

    function createTimeseriesDatasets(timeseriesData) {
        return timeseriesData.agents.map(function(agent) {
            return {
                label: 'Agent ' + agent.agent_id,
                data: agent.data,
                borderColor: agent.color,
                backgroundColor: agent.color.replace('0.7', '0.1'),
                borderWidth: 1.5,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.3,
                spanGaps: false
            };
        });
    }

    var verticalLinePlugin = {
        id: 'verticalLineMarker',
        afterDraw: function(chart) {
            if (chart.config.options.plugins.verticalLine && chart.config.options.plugins.verticalLine.x !== undefined) {
                var ctx2 = chart.ctx;
                var x = chart.config.options.plugins.verticalLine.x;
                var yScale = chart.scales.y;
                ctx2.save();
                ctx2.beginPath();
                ctx2.strokeStyle = chart.config.options.plugins.verticalLine.color || 'rgba(255, 0, 0, 0.8)';
                ctx2.lineWidth = chart.config.options.plugins.verticalLine.width || 2;
                ctx2.setLineDash([5, 5]);
                ctx2.moveTo(x, yScale.top);
                ctx2.lineTo(x, yScale.bottom);
                ctx2.stroke();
                ctx2.restore();
            }
        }
    };

    function updateEvoChart(data) {
        if (_evoChartInstance) {
            var total = data.chart_values.reduce(function(a, b) { return a + b; }, 0);
            var percentages = data.chart_values.map(function(val) { return total > 0 ? (val / total * 100) : 0; });
            var maxPercentage = percentages.length > 0 ? Math.max.apply(null, percentages) : 0;
            var yAxisMax = maxPercentage * 1.05;
            _evoChartInstance.data.labels = data.chart_labels;
            _evoChartInstance.data.datasets[0].data = percentages;
            _evoChartInstance.options.scales.y.max = yAxisMax;
            _evoChartValues.length = 0;
            _evoChartValues.push.apply(_evoChartValues, data.chart_values);
            _evoChartInstance.update('none');
        }

        if (_evoGroupTrendsChartInstance) {
            if (data.group_trends_data) {
                _currentGroupTrendsData = data.group_trends_data;
                _evoGroupTrendsChartInstance.data.labels = data.group_trends_data.timestamps || [];
                _evoGroupTrendsChartInstance.data.datasets = createGroupTrendsDatasets(data.group_trends_data);
            }
            var currentDay = data.filter_day;
            var labels = _evoGroupTrendsChartInstance.data.labels || [];
            var dayIndex = labels.findIndex(function(label) { return Math.floor(label) === Math.floor(currentDay); });
            if (dayIndex !== -1) {
                var xScale = _evoGroupTrendsChartInstance.scales.x;
                var xPixel = xScale.getPixelForValue(dayIndex);
                _evoGroupTrendsChartInstance.options.plugins.verticalLine.x = xPixel;
                _evoGroupTrendsChartInstance.update('none');
            }
        }

        if (_evoTimeseriesChartInstance && data.timeseries_data) {
            _currentTimeseriesData = data.timeseries_data;
            _evoTimeseriesChartInstance.data.labels = data.timeseries_data.timestamps;
            _evoTimeseriesChartInstance.data.datasets = createTimeseriesDatasets(data.timeseries_data);
            _evoTimeseriesChartInstance.update('none');
        }

        document.getElementById('total-opinions').textContent = data.total_opinions;
        document.getElementById('social-interactions').textContent = data.social_interactions;
        document.getElementById('unique-agents').textContent = data.unique_agents;
        document.getElementById('current-day').textContent = data.filter_day;
        document.getElementById('current-hour').textContent = data.filter_hour;
    }

    function fetchOpinionData(day, hour, topicId, skipTrends) {
        if (skipTrends === undefined) skipTrends = true;
        var config = window.YS_DATA_EVOLUTION || {};
        var expId = config.expId;
        _loadingTimeout = setTimeout(function() {
            document.getElementById('loading-overlay').classList.add('active');
        }, 200);

        var url = '/admin/opinion_evolution_data/' + expId + '?day=' + day + '&hour=' + hour + '&sample_percentage=' + _currentSamplePercentage;
        if (topicId && topicId !== '') url += '&topic_id=' + topicId;
        if (skipTrends) url += '&skip_trends=true';

        fetch(url)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                clearTimeout(_loadingTimeout);
                document.getElementById('loading-overlay').classList.remove('active');
                updateEvoChart(data);
            })
            .catch(function(error) {
                console.error('Error fetching opinion data:', error);
                clearTimeout(_loadingTimeout);
                document.getElementById('loading-overlay').classList.remove('active');
            });
    }

    function getGranularityStep() {
        switch (_currentGranularity) {
            case 'hourly': return 1;
            case 'daily': return 24;
            case 'weekly': return 168;
            default: return 1;
        }
    }

    function snapToGranularity(value) {
        var step = getGranularityStep();
        if (step === 1) return value;
        var day = Math.floor(value / 24);
        if (_currentGranularity === 'daily') return day * 24;
        if (_currentGranularity === 'weekly') {
            var week = Math.floor(day / 7);
            return week * 168;
        }
        return value;
    }

    function getCurrentInterval() {
        return _baseInterval / _speeds[_currentSpeedIndex];
    }

    function updateSpeedDisplay() {
        document.getElementById('speed-display').textContent = _speeds[_currentSpeedIndex] + 'x';
        document.getElementById('speed-down').disabled = _currentSpeedIndex === 0;
        document.getElementById('speed-up').disabled = _currentSpeedIndex === _speeds.length - 1;
    }

    function playStep(timeSlider, playButton, playIcon) {
        var currentValue = parseInt(timeSlider.value);
        var step = getGranularityStep();
        if (currentValue >= _maxTimeValue) {
            _isPlaying = false;
            clearInterval(_playInterval);
            playButton.classList.remove('playing');
            playIcon.classList.remove('mdi-pause');
            playIcon.classList.add('mdi-play');
            playButton.title = 'Play';
            return;
        }
        currentValue += step;
        if (currentValue > _maxTimeValue) currentValue = _maxTimeValue;
        timeSlider.value = currentValue;
        var day = Math.floor(currentValue / 24);
        var hour = currentValue % 24;
        fetchOpinionData(day, hour, _currentTopicId);
    }

    function restartPlayInterval(timeSlider, playButton, playIcon) {
        clearInterval(_playInterval);
        _playInterval = setInterval(function() { playStep(timeSlider, playButton, playIcon); }, getCurrentInterval());
    }

    function initOpinionEvolution() {
        var config = window.YS_DATA_EVOLUTION || {};
        var chartLabels = config.chartLabels || [];
        var chartValues = config.chartValues || [];
        var groupTrendsData = config.groupTrendsData || { groups: [], timestamps: [], timestamp_mapping: {} };
        var timeseriesData = config.timeseriesData || { agents: [], timestamps: [] };
        _currentTopicId = config.filterTopicId || null;
        _maxTimeValue = config.maxTick || ((config.maxDay || 0) * 24 + (config.maxHour || 0));

        _evoChartValues.push.apply(_evoChartValues, chartValues);

        var totalAgents = chartValues.reduce(function(a, b) { return a + b; }, 0);
        var chartPercentages = chartValues.map(function(val) { return totalAgents > 0 ? (val / totalAgents * 100) : 0; });
        var maxPercentage = chartPercentages.length > 0 ? Math.max.apply(null, chartPercentages) : 0;
        var yAxisMax = maxPercentage * 1.05;
        var colorSet = generateChartColors(chartLabels.length);

        var ctx = document.getElementById('opinionChart').getContext('2d');
        _evoChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartLabels,
                datasets: [{
                    label: 'Percentage of Agents',
                    data: chartPercentages,
                    backgroundColor: colorSet.colors,
                    borderColor: colorSet.borderColors,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: { duration: 0 },
                plugins: {
                    legend: { display: false },
                    title: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                var percentage = context.parsed.y.toFixed(1);
                                var agentCount = _evoChartValues[context.dataIndex];
                                return percentage + '% (' + agentCount + ' agents)';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: yAxisMax,
                        ticks: { callback: function(value) { return value.toFixed(1) + '%'; } },
                        title: { display: true, text: 'Percentage of Agents' }
                    },
                    x: { title: { display: true, text: 'Opinion Group' } }
                }
            }
        });

        var groupTrendsCtx = document.getElementById('groupTrendsChart').getContext('2d');
        _currentGroupTrendsData = groupTrendsData;
        _evoGroupTrendsChartInstance = new Chart(groupTrendsCtx, {
            type: 'line',
            data: {
                labels: groupTrendsData.timestamps,
                datasets: createGroupTrendsDatasets(groupTrendsData)
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: { duration: 0 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    verticalLine: { x: null, color: 'rgba(255, 99, 71, 0.9)', width: 3 },
                    legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 10 }, padding: 8 } },
                    title: { display: false },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        callbacks: {
                            title: function(context) {
                                var position = context[0].label;
                                var mapping = (_currentGroupTrendsData && _currentGroupTrendsData.timestamp_mapping)
                                    ? _currentGroupTrendsData.timestamp_mapping[position]
                                    : null;
                                if (mapping) return 'Day ' + mapping.day + ', Hour ' + mapping.hour;
                                return 'Step ' + position;
                            },
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        max: 100,
                        ticks: { callback: function(value) { return value.toFixed(0) + '%'; } },
                        title: { display: true, text: 'Percentage of Agents' }
                    },
                    x: {
                        type: 'category',
                        stacked: true,
                        title: { display: true, text: 'Simulation Days' },
                        ticks: { maxTicksLimit: 10 }
                    }
                }
            },
            plugins: [verticalLinePlugin]
        });

        var timeseriesCtx = document.getElementById('timeseriesChart').getContext('2d');
        _currentTimeseriesData = timeseriesData;
        _evoTimeseriesChartInstance = new Chart(timeseriesCtx, {
            type: 'line',
            data: {
                labels: timeseriesData.timestamps,
                datasets: createTimeseriesDatasets(timeseriesData)
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: { duration: 0 },
                interaction: { mode: 'nearest', axis: 'x', intersect: false },
                plugins: {
                    legend: { display: false },
                    title: { display: false },
                    tooltip: { enabled: false }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        min: 0,
                        max: 1,
                        ticks: { stepSize: 0.2 },
                        title: { display: true, text: 'Opinion Value' }
                    },
                    x: {
                        type: 'category',
                        title: { display: true, text: 'Simulation Days' },
                        ticks: { maxTicksLimit: 10 }
                    }
                }
            }
        });

        var initialSlider = document.getElementById('time-slider');
        if (_evoGroupTrendsChartInstance && initialSlider) {
            var initialValue = parseInt(initialSlider.value, 10);
            if (!isNaN(initialValue)) {
                var initialDay = Math.floor(initialValue / 24);
                var initialLabels = _evoGroupTrendsChartInstance.data.labels || [];
                var initialDayIndex = initialLabels.findIndex(function(label) {
                    return Math.floor(label) === Math.floor(initialDay);
                });
                if (initialDayIndex !== -1) {
                    var initialScale = _evoGroupTrendsChartInstance.scales.x;
                    _evoGroupTrendsChartInstance.options.plugins.verticalLine.x =
                        initialScale.getPixelForValue(initialDayIndex);
                    _evoGroupTrendsChartInstance.update('none');
                }
            }
        }

        updateSpeedDisplay();

        var timeSlider = document.getElementById('time-slider');
        var sampleInput = document.getElementById('sample-input');
        var playButton = document.getElementById('play-button');
        var playIcon = playButton.querySelector('i');
        var sliderTimeout = null;
        var sampleInputTimeout = null;

        timeSlider.addEventListener('input', function() {
            var totalHours = parseInt(this.value);
            var day = Math.floor(totalHours / 24);
            var hour = totalHours % 24;
            clearTimeout(sliderTimeout);
            sliderTimeout = setTimeout(function() { fetchOpinionData(day, hour, _currentTopicId); }, 300);
        });

        sampleInput.addEventListener('input', function() {
            var percentage = parseInt(this.value);
            if (this.value === '' || isNaN(percentage)) return;
            if (percentage < 1) { percentage = 1; this.value = 1; }
            else if (percentage > 100) { percentage = 100; this.value = 100; }
            _currentSamplePercentage = percentage;
            clearTimeout(sampleInputTimeout);
            sampleInputTimeout = setTimeout(function() {
                var totalHours = parseInt(timeSlider.value);
                var day = Math.floor(totalHours / 24);
                var hour = totalHours % 24;
                fetchOpinionData(day, hour, _currentTopicId);
            }, 300);
        });

        document.querySelectorAll('.topic-tag').forEach(function(tag) {
            tag.addEventListener('click', function() {
                document.querySelectorAll('.topic-tag').forEach(function(t) { t.classList.remove('active'); });
                this.classList.add('active');
                _currentTopicId = this.dataset.topicId;
                var totalHours = parseInt(timeSlider.value);
                var day = Math.floor(totalHours / 24);
                var hour = totalHours % 24;
                fetchOpinionData(day, hour, _currentTopicId, false);
            });
        });

        playButton.addEventListener('click', function() {
            if (_isPlaying) {
                _isPlaying = false;
                clearInterval(_playInterval);
                playButton.classList.remove('playing');
                playIcon.classList.remove('mdi-pause');
                playIcon.classList.add('mdi-play');
                playButton.title = 'Play';
            } else {
                _isPlaying = true;
                playButton.classList.add('playing');
                playIcon.classList.remove('mdi-play');
                playIcon.classList.add('mdi-pause');
                playButton.title = 'Pause';
                playStep(timeSlider, playButton, playIcon);
                _playInterval = setInterval(function() { playStep(timeSlider, playButton, playIcon); }, getCurrentInterval());
            }
        });

        bindById('speed-down', 'click', function() {
            if (_currentSpeedIndex > 0) {
                _currentSpeedIndex--;
                updateSpeedDisplay();
                if (_isPlaying) restartPlayInterval(timeSlider, playButton, playIcon);
            }
        });

        bindById('speed-up', 'click', function() {
            if (_currentSpeedIndex < _speeds.length - 1) {
                _currentSpeedIndex++;
                updateSpeedDisplay();
                if (_isPlaying) restartPlayInterval(timeSlider, playButton, playIcon);
            }
        });

        document.querySelectorAll('.granularity-button').forEach(function(button) {
            button.addEventListener('click', function() {
                document.querySelectorAll('.granularity-button').forEach(function(btn) {
                    btn.style.background = 'white';
                    btn.style.color = '#374151';
                    btn.classList.remove('active');
                });
                this.style.background = '#039be5';
                this.style.color = 'white';
                this.classList.add('active');
                _currentGranularity = this.dataset.granularity;
                timeSlider.step = getGranularityStep();
                var currentValue = parseInt(timeSlider.value);
                var snappedValue = snapToGranularity(currentValue);
                if (snappedValue !== currentValue) {
                    timeSlider.value = snappedValue;
                    var day = Math.floor(snappedValue / 24);
                    var hour = snappedValue % 24;
                    fetchOpinionData(day, hour, _currentTopicId);
                }
            });
        });
    }

    return {
        initOpinionConfiguration: initOpinionConfiguration,
        selectUpdateRule: selectUpdateRule,
        toggleUpdateRuleOptions: toggleUpdateRuleOptions,
        initOpinionEvolution: initOpinionEvolution
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('distributions-grid')) {
        AdminOpinion.initOpinionConfiguration();
    }
    if (document.getElementById('opinionChart')) {
        AdminOpinion.initOpinionEvolution();
    }
});

window.selectUpdateRule = AdminOpinion.selectUpdateRule;
