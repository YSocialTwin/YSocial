(function() {
  let stressChart = null;
  let rewardChart = null;
  let trendChart = null;
  let saTargetChart = null;
  let currentGranularity = 'hourly';
  let isPlaying = false;
  let playInterval = null;
  let currentSpeedIndex = 2;
  const speeds = [0.5, 0.75, 1, 1.5, 2, 4];
  const baseInterval = 1200;
  let loadingTimeout = null;

  function getConfig() {
    return window.YS_DATA_STRESS_REWARD || {};
  }

  function getGranularityStep() {
    if (currentGranularity === 'daily') return 24;
    if (currentGranularity === 'weekly') return 168;
    return 1;
  }

  function snapToGranularity(value) {
    const step = getGranularityStep();
    if (step === 1) return value;
    const day = Math.floor(value / 24);
    if (currentGranularity === 'daily') return day * 24;
    return Math.floor(day / 7) * 168;
  }

  function updateSpeedDisplay() {
    document.getElementById('sr-speed-display').textContent = speeds[currentSpeedIndex] + 'x';
    document.getElementById('sr-speed-down').disabled = currentSpeedIndex === 0;
    document.getElementById('sr-speed-up').disabled = currentSpeedIndex === speeds.length - 1;
  }

  function getCurrentInterval() {
    return baseInterval / speeds[currentSpeedIndex];
  }

  function buildBarChart(canvasId, label, labels, values, colors) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: label,
          data: values,
          backgroundColor: colors.background,
          borderColor: colors.border,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: { duration: 0 },
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            title: { display: true, text: 'Agents' }
          },
          x: {
            title: { display: true, text: 'Aggregate Level' }
          }
        }
      }
    });
  }

  function buildTrendChart(trendData) {
    const ctx = document.getElementById('stressRewardTrendChart').getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: trendData.timestamps || [],
        datasets: [
          {
            label: 'Average Stress',
            data: ((trendData.datasets || [])[0] || {}).data || [],
            borderColor: 'rgba(239, 68, 68, 1)',
            backgroundColor: 'rgba(239, 68, 68, 0.18)',
            fill: false,
            tension: 0.25
          },
          {
            label: 'Average Reward',
            data: ((trendData.datasets || [])[1] || {}).data || [],
            borderColor: 'rgba(34, 197, 94, 1)',
            backgroundColor: 'rgba(34, 197, 94, 0.18)',
            fill: false,
            tension: 0.25
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: { duration: 0 },
        plugins: {
          legend: { display: true, position: 'bottom' },
          tooltip: {
            callbacks: {
              title: function(context) {
                const key = context[0].label;
                const mapping = (trendData.timestamp_mapping || {})[key];
                if (mapping) return 'Day ' + mapping.day + ', Hour ' + mapping.hour;
                return 'Step ' + key;
              },
              label: function(context) {
                return context.dataset.label + ': ' + Number(context.parsed.y || 0).toFixed(3);
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 1,
            title: { display: true, text: 'Average Aggregate Value' }
          },
          x: {
            title: { display: true, text: 'Simulation Days' }
          }
        }
      }
    });
  }

  function buildSaTargetChart(targetData) {
    const ctx = document.getElementById('srSaTargetTrendChart').getContext('2d');
    return new Chart(ctx, {
      data: {
        labels: targetData.timestamps || [],
        datasets: [
          {
            type: 'line',
            label: 'Target Stress',
            data: ((targetData.datasets || [])[0] || {}).data || [],
            borderColor: 'rgba(239, 68, 68, 1)',
            backgroundColor: 'rgba(239, 68, 68, 0.16)',
            fill: false,
            tension: 0.25,
            yAxisID: 'y'
          },
          {
            type: 'line',
            label: 'Target Reward',
            data: ((targetData.datasets || [])[1] || {}).data || [],
            borderColor: 'rgba(34, 197, 94, 1)',
            backgroundColor: 'rgba(34, 197, 94, 0.16)',
            fill: false,
            tension: 0.25,
            yAxisID: 'y'
          },
          {
            type: 'bar',
            label: 'SA Interactions',
            data: ((targetData.datasets || [])[2] || {}).data || [],
            borderColor: 'rgba(245, 158, 11, 1)',
            backgroundColor: 'rgba(245, 158, 11, 0.4)',
            borderWidth: 1,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: { duration: 0 },
        plugins: {
          legend: { display: true, position: 'bottom' },
          tooltip: {
            callbacks: {
              title: function(context) {
                const key = context[0].label;
                const mapping = (targetData.timestamp_mapping || {})[key];
                if (mapping) return 'Day ' + mapping.day + ', Hour ' + mapping.hour;
                return 'Step ' + key;
              },
              label: function(context) {
                if (context.dataset.label === 'SA Interactions') {
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
            title: { display: true, text: 'Aggregate Value' }
          },
          y1: {
            beginAtZero: true,
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { precision: 0 },
            title: { display: true, text: 'Interactions' }
          },
          x: {
            title: { display: true, text: 'Simulation Days' }
          }
        }
      }
    });
  }

  function updateSaTargetSection(saTargets) {
    const panel = document.getElementById('sr-sa-target-panel');
    if (!panel) return;

    const options = saTargets.options || [];
    const select = document.getElementById('sr-sa-target-select');
    const emptyState = document.getElementById('sr-sa-empty-state');
    const chartColumn = document.getElementById('sr-sa-chart-column');
    const eventsColumn = document.getElementById('sr-sa-events-column');
    const deployed = document.getElementById('sr-sa-deployed');
    if (deployed) deployed.textContent = saTargets.deployed_agents || 0;
    if (!select) return;

    const hasOptions = options.length > 0;
    select.disabled = !hasOptions;
    if (emptyState) {
      emptyState.style.display = hasOptions ? 'none' : '';
    }
    if (chartColumn) {
      chartColumn.style.display = hasOptions ? '' : 'none';
    }
    if (eventsColumn) {
      eventsColumn.style.display = hasOptions ? '' : 'none';
    }

    const currentSelection = saTargets.selected_uid || '';
    select.innerHTML = options.map(function(option) {
      const selected = option.uid === currentSelection ? ' selected' : '';
      return '<option value="' + option.uid + '"' + selected + '>' +
        option.username + ' (' + option.interaction_count + ' interactions)</option>';
    }).join('');

    const targetName = document.getElementById('sr-sa-target-name');
    const interactionCount = document.getElementById('sr-sa-interaction-count');
    const attackerNames = document.getElementById('sr-sa-attacker-names');
    if (targetName) targetName.textContent = hasOptions ? (saTargets.selected_username || '—') : '—';
    if (interactionCount) interactionCount.textContent = hasOptions ? (saTargets.interaction_count || 0) : 0;
    if (attackerNames) attackerNames.textContent = hasOptions ? ((saTargets.attacker_usernames || []).join(', ') || '—') : '—';

    const eventTable = document.getElementById('sr-sa-events-body');
    if (eventTable) {
      const events = saTargets.interaction_events || [];
      eventTable.innerHTML = events.length
        ? events.map(function(event) {
            return '<tr>' +
              '<td>Day ' + event.day + ', Hour ' + event.hour + '</td>' +
              '<td>' + String(event.interaction_type || '').charAt(0).toUpperCase() + String(event.interaction_type || '').slice(1) + '</td>' +
              '<td>' + (event.interaction_count || 0) + '</td>' +
              '<td>' + ((event.attacker_usernames || []).join(', ') || '—') + '</td>' +
              '</tr>';
          }).join('')
        : '<tr><td colspan=\"4\">No SA interactions recorded up to the selected time.</td></tr>';
    }

    const targetData = saTargets.trend_data || { timestamps: [], datasets: [], timestamp_mapping: {} };
    if (!hasOptions && saTargetChart) {
      saTargetChart.data.labels = [];
      saTargetChart.data.datasets[0].data = [];
      saTargetChart.data.datasets[1].data = [];
      saTargetChart.data.datasets[2].data = [];
      saTargetChart.update('none');
      return;
    }
    if (!hasOptions) {
      return;
    }

    if (!saTargetChart && document.getElementById('srSaTargetTrendChart')) {
      saTargetChart = buildSaTargetChart(targetData);
      return;
    }
    if (!saTargetChart) return;

    saTargetChart.data.labels = targetData.timestamps || [];
    saTargetChart.data.datasets[0].data = ((targetData.datasets || [])[0] || {}).data || [];
    saTargetChart.data.datasets[1].data = ((targetData.datasets || [])[1] || {}).data || [];
    saTargetChart.data.datasets[2].data = ((targetData.datasets || [])[2] || {}).data || [];
    saTargetChart.options.plugins.tooltip.callbacks.title = function(context) {
      const key = context[0].label;
      const mapping = (targetData.timestamp_mapping || {})[key];
      if (mapping) return 'Day ' + mapping.day + ', Hour ' + mapping.hour;
      return 'Step ' + key;
    };
    saTargetChart.update('none');
  }

  function updateView(data) {
    const snapshot = data.snapshot || {};
    const trendData = data.trend_data || { timestamps: [], datasets: [], timestamp_mapping: {} };

    stressChart.data.labels = snapshot.stress_labels || [];
    stressChart.data.datasets[0].data = snapshot.stress_values || [];
    stressChart.update('none');

    rewardChart.data.labels = snapshot.reward_labels || [];
    rewardChart.data.datasets[0].data = snapshot.reward_values || [];
    rewardChart.update('none');

    trendChart.data.labels = trendData.timestamps || [];
    trendChart.data.datasets[0].data = ((trendData.datasets || [])[0] || {}).data || [];
    trendChart.data.datasets[1].data = ((trendData.datasets || [])[1] || {}).data || [];
    trendChart.options.plugins.tooltip.callbacks.title = function(context) {
      const key = context[0].label;
      const mapping = (trendData.timestamp_mapping || {})[key];
      if (mapping) return 'Day ' + mapping.day + ', Hour ' + mapping.hour;
      return 'Step ' + key;
    };
    trendChart.update('none');

    document.getElementById('sr-average-stress').textContent = Number(snapshot.average_stress || 0).toFixed(3);
    document.getElementById('sr-average-reward').textContent = Number(snapshot.average_reward || 0).toFixed(3);
    document.getElementById('sr-unique-agents').textContent = snapshot.unique_agents || 0;
    document.getElementById('sr-aggregate-rows').textContent = snapshot.aggregate_rows || 0;
    document.getElementById('sr-current-day').textContent = data.filter_day;
    document.getElementById('sr-current-hour').textContent = data.filter_hour;

    if (data.sa_targets) {
      updateSaTargetSection(data.sa_targets);
    }
  }

  function fetchStressRewardData(day, hour) {
    const config = getConfig();
    const targetSelect = document.getElementById('sr-sa-target-select');
    const targetUid = targetSelect ? targetSelect.value : '';
    loadingTimeout = setTimeout(function() {
      document.getElementById('sr-loading-overlay').classList.add('active');
    }, 200);

    let url = '/admin/stress_reward_evolution_data/' + config.expId + '?day=' + day + '&hour=' + hour;
    if (targetUid) {
      url += '&target_uid=' + encodeURIComponent(targetUid);
    }

    fetch(url)
      .then(function(response) { return response.json(); })
      .then(function(data) {
        clearTimeout(loadingTimeout);
        document.getElementById('sr-loading-overlay').classList.remove('active');
        updateView(data);
      })
      .catch(function(error) {
        console.error('Error fetching stress/reward data:', error);
        clearTimeout(loadingTimeout);
        document.getElementById('sr-loading-overlay').classList.remove('active');
      });
  }

  function playStep(slider, playButton, playIcon) {
    let currentValue = parseInt(slider.value, 10);
    const maxValue = getConfig().maxTick || 0;
    const step = getGranularityStep();
    if (currentValue >= maxValue) {
      isPlaying = false;
      clearInterval(playInterval);
      playButton.classList.remove('playing');
      playIcon.classList.remove('mdi-pause');
      playIcon.classList.add('mdi-play');
      playButton.title = 'Play';
      return;
    }
    currentValue += step;
    if (currentValue > maxValue) currentValue = maxValue;
    slider.value = currentValue;
    fetchStressRewardData(Math.floor(currentValue / 24), currentValue % 24);
  }

  function restartPlayInterval(slider, playButton, playIcon) {
    clearInterval(playInterval);
    playInterval = setInterval(function() {
      playStep(slider, playButton, playIcon);
    }, getCurrentInterval());
  }

  function init() {
    if (!document.getElementById('stressDistributionChart')) return;
    const config = getConfig();
    const snapshot = config.snapshot || {};
    const trendData = config.trendData || { timestamps: [], datasets: [], timestamp_mapping: {} };
    const saTargets = config.saTargets || null;

    stressChart = buildBarChart(
      'stressDistributionChart',
      'Stress',
      snapshot.stress_labels || [],
      snapshot.stress_values || [],
      { background: 'rgba(239, 68, 68, 0.72)', border: 'rgba(220, 38, 38, 1)' }
    );
    rewardChart = buildBarChart(
      'rewardDistributionChart',
      'Reward',
      snapshot.reward_labels || [],
      snapshot.reward_values || [],
      { background: 'rgba(34, 197, 94, 0.72)', border: 'rgba(22, 163, 74, 1)' }
    );
    trendChart = buildTrendChart(trendData);
    if (saTargets && saTargets.available && document.getElementById('srSaTargetTrendChart')) {
      updateSaTargetSection(saTargets);
    }
    updateSpeedDisplay();

    const slider = document.getElementById('sr-time-slider');
    const playButton = document.getElementById('sr-play-button');
    const playIcon = playButton.querySelector('i');
    let sliderTimeout = null;

    slider.addEventListener('input', function() {
      const totalHours = parseInt(this.value, 10);
      clearTimeout(sliderTimeout);
      sliderTimeout = setTimeout(function() {
        fetchStressRewardData(Math.floor(totalHours / 24), totalHours % 24);
      }, 300);
    });

    const saTargetSelect = document.getElementById('sr-sa-target-select');
    if (saTargetSelect) {
      saTargetSelect.addEventListener('change', function() {
        const totalHours = parseInt(slider.value, 10);
        fetchStressRewardData(Math.floor(totalHours / 24), totalHours % 24);
      });
    }

    playButton.addEventListener('click', function() {
      if (isPlaying) {
        isPlaying = false;
        clearInterval(playInterval);
        playButton.classList.remove('playing');
        playIcon.classList.remove('mdi-pause');
        playIcon.classList.add('mdi-play');
        playButton.title = 'Play';
      } else {
        isPlaying = true;
        playButton.classList.add('playing');
        playIcon.classList.remove('mdi-play');
        playIcon.classList.add('mdi-pause');
        playButton.title = 'Pause';
        playStep(slider, playButton, playIcon);
        playInterval = setInterval(function() {
          playStep(slider, playButton, playIcon);
        }, getCurrentInterval());
      }
    });

    document.getElementById('sr-speed-down').addEventListener('click', function() {
      if (currentSpeedIndex > 0) {
        currentSpeedIndex -= 1;
        updateSpeedDisplay();
        if (isPlaying) restartPlayInterval(slider, playButton, playIcon);
      }
    });
    document.getElementById('sr-speed-up').addEventListener('click', function() {
      if (currentSpeedIndex < speeds.length - 1) {
        currentSpeedIndex += 1;
        updateSpeedDisplay();
        if (isPlaying) restartPlayInterval(slider, playButton, playIcon);
      }
    });

    document.querySelectorAll('.sr-granularity-button').forEach(function(button) {
      button.addEventListener('click', function() {
        document.querySelectorAll('.sr-granularity-button').forEach(function(btn) {
          btn.style.background = 'white';
          btn.style.color = '#374151';
          btn.classList.remove('active');
        });
        this.style.background = '#039be5';
        this.style.color = 'white';
        this.classList.add('active');
        currentGranularity = this.dataset.granularity;
        slider.step = getGranularityStep();
        const currentValue = parseInt(slider.value, 10);
        const snapped = snapToGranularity(currentValue);
        if (snapped !== currentValue) {
          slider.value = snapped;
          fetchStressRewardData(Math.floor(snapped / 24), snapped % 24);
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
