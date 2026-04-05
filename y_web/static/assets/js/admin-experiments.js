/**
 * AdminExperiments - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminExperiments = (function() {
  const byId = (id) => document.getElementById(id);
  const bindById = (id, eventName, handler) => {
      const element = byId(id);
      if (element) {
          element.addEventListener(eventName, handler);
      }
      return element;
  };
  const currentExperimentData = () => window.YS_DATA_EXP_FORUM || window.YS_DATA_EXP || {};

  (function() {
      const toxicityToggle = document.getElementById('toxicity_annotation_toggle_exp');
      const perspectiveWrap = document.getElementById('perspective_api_field_exp');
      const perspectiveInput = document.getElementById('perspective_api_input_exp');
      if (!toxicityToggle || !perspectiveWrap || !perspectiveInput) return;
      const syncPerspectiveState = () => {
          const enabled = !!toxicityToggle.checked;
          perspectiveInput.disabled = !enabled;
          perspectiveWrap.classList.toggle('perspective-field-disabled', !enabled);
          if (!enabled) {
              perspectiveInput.value = '';
          }
      };
      toxicityToggle.addEventListener('change', syncPerspectiveState);
      syncPerspectiveState();
  })();

  (function() {
      const tags = document.getElementById('experiment-topics-tags');
      const hiddenInput = document.getElementById('experiment-topics-hidden');
      const input = document.getElementById('experiment-topics-input');
      if (!tags || !hiddenInput || !input) return;

      const tagList = hiddenInput.value
          ? hiddenInput.value.split(',').map(item => item.trim()).filter(Boolean)
          : [];

      function syncHiddenInput() {
          hiddenInput.value = tagList.join(',');
      }

      function createTagElement(tagContent) {
          const tag = document.createElement('li');
          tag.appendChild(document.createTextNode(`${tagContent} `));
          const deleteBtn = document.createElement('button');
          deleteBtn.type = 'button';
          deleteBtn.className = 'delete-button';
          deleteBtn.textContent = 'X';
          tag.appendChild(deleteBtn);
          return tag;
      }

      function addTagFromInput() {
          const tagContent = input.value.trim();
          if (!tagContent) return;
          const duplicate = tagList.some(existing => existing.toLowerCase() === tagContent.toLowerCase());
          if (duplicate) {
              input.value = '';
              return;
          }
          tagList.push(tagContent);
          tags.appendChild(createTagElement(tagContent));
          syncHiddenInput();
          input.value = '';
      }

      input.addEventListener('keydown', function(event) {
          if (event.key === 'Enter') {
              event.preventDefault();
              addTagFromInput();
          }
      });

      tags.addEventListener('click', function(event) {
          if (!event.target.classList.contains('delete-button')) return;
          const tagText = event.target.parentNode.textContent.slice(0, -1).trim();
          const idx = tagList.findIndex(item => item.toLowerCase() === tagText.toLowerCase());
          if (idx >= 0) {
              tagList.splice(idx, 1);
          }
          event.target.parentNode.remove();
          syncHiddenInput();
      });
  })();

  // Experiment server control functions
  function startExperimentServer(expId) {
      showLoading('Starting experiment server...');
      window.location.href = `/admin/start_experiment/${expId}`;
  }

  function stopExperimentServer(expId) {
      showLoading('Stopping experiment server...');
      window.location.href = `/admin/stop_experiment/${expId}`;
  }

  function selectExperiment(expId) {
      showLoading('Loading experiment interface...');
      window.location.href = `/admin/select_experiment/${expId}`;
  }

  function joinExperiment(expId) {
      showLoading('Joining experiment...');
      window.location.href = `/admin/join_experiment/${expId}`;
  }

  function startJupyter(expId) {
      showLoading('Starting JupyterLab...');
      fetch(`/admin/lab_start/${expId}`)
          .then(response => response.json())
          .then(data => {
              location.reload();
          })
          .catch(error => {
              console.error('Error starting JupyterLab:', error);
              hideLoading();
              showToast('Error starting JupyterLab', 'error');
              setTimeout(() => location.reload(), 1500);
          });
  }

  function stopJupyter(instanceId) {
      showLoading('Stopping JupyterLab...');
      fetch(`/admin/lab_stop/${instanceId}`)
          .then(response => response.json())
          .then(data => {
              location.reload();
          })
          .catch(error => {
              console.error('Error stopping JupyterLab:', error);
              hideLoading();
              showToast('Error stopping JupyterLab', 'error');
              setTimeout(() => location.reload(), 1500);
          });
  }

  // Global variables to store client charts and data
  let clientCallVolumeChartInstance = null;
  let clientMeanExecutionTimeChartInstance = null;
  let allClientMethodsData = {
      methods: [],
      callVolume: {},
      meanExecutionTime: {}
  };
  let clientLogsAutoRefreshInterval = null;

  // Function to update client charts based on selected methods
  function updateClientCharts() {
      const checkboxes = document.querySelectorAll('#methodFilters input[type="checkbox"]');
      const selectedMethods = [];
    
      checkboxes.forEach(checkbox => {
          if (checkbox.checked) {
              selectedMethods.push(checkbox.value);
          }
      });

      // If no methods selected, show all
      const methodsToShow = selectedMethods.length > 0 ? selectedMethods : allClientMethodsData.methods;
    
      // Prepare filtered data
      const volumeData = methodsToShow.map(method => allClientMethodsData.callVolume[method] || 0);
      const executionTimeData = methodsToShow.map(method => allClientMethodsData.meanExecutionTime[method] || 0);

      // Update Call Volume Chart
      if (clientCallVolumeChartInstance) {
          clientCallVolumeChartInstance.data.labels = methodsToShow;
          clientCallVolumeChartInstance.data.datasets[0].data = volumeData;
          clientCallVolumeChartInstance.update();
      }

      // Update Mean Execution Time Chart
      if (clientMeanExecutionTimeChartInstance) {
          clientMeanExecutionTimeChartInstance.data.labels = methodsToShow;
          clientMeanExecutionTimeChartInstance.data.datasets[0].data = executionTimeData;
          clientMeanExecutionTimeChartInstance.update();
      }
  }

  // Function to create method filter checkboxes
  function createMethodFilters(methods) {
      const filterContainer = document.getElementById('methodFilters');
      filterContainer.innerHTML = '';
    
      methods.forEach(method => {
          const label = document.createElement('label');
        
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = method;
          checkbox.checked = true;
          checkbox.addEventListener('change', updateClientCharts);
        
          const span = document.createElement('span');
          span.textContent = method;
        
          label.appendChild(checkbox);
          label.appendChild(span);
          filterContainer.appendChild(label);
      });
  }

  // Function to load client logs
  function loadClientLogs(clientId) {
      // Clear previous data
      if (clientCallVolumeChartInstance) {
          clientCallVolumeChartInstance.destroy();
          clientCallVolumeChartInstance = null;
      }
      if (clientMeanExecutionTimeChartInstance) {
          clientMeanExecutionTimeChartInstance.destroy();
          clientMeanExecutionTimeChartInstance = null;
      }

      // Hide content and error initially
      const clientLogsContent = document.getElementById('client-logs-content');
      const clientLogsError = document.getElementById('client-logs-error-message');
      if (clientLogsContent) {
          clientLogsContent.classList.add('d-none');
          clientLogsContent.style.display = 'none';
      }
      if (clientLogsError) {
          clientLogsError.style.display = 'none';
      }

      if (!clientId) {
          return;
      }

      // Disable refresh button while loading
      const refreshBtn = document.getElementById('refreshClientLogsBtn');
      if (refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Loading...';
      }

      // Fetch and display client logs data
      fetch(`/admin/client_logs/${clientId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  if (clientLogsError) {
                      clientLogsError.style.display = 'block';
                  }
                  document.getElementById('client-logs-error-text').textContent = data.error;
                  return;
              }

              const callVolume = data.call_volume || {};
              const meanExecutionTime = data.mean_execution_time || {};

              // Check if there's any data
              if (Object.keys(callVolume).length === 0) {
                  if (clientLogsError) {
                      clientLogsError.style.display = 'block';
                  }
                  document.getElementById('client-logs-error-text').textContent = 'No log data available for this client.';
                  return;
              }

              // Show content
              if (clientLogsContent) {
                  clientLogsContent.classList.remove('d-none');
                  clientLogsContent.style.display = 'block';
              }

              // Store data globally
              allClientMethodsData.methods = Object.keys(callVolume).sort();
              allClientMethodsData.callVolume = callVolume;
              allClientMethodsData.meanExecutionTime = meanExecutionTime;

              // Create filter checkboxes
              createMethodFilters(allClientMethodsData.methods);

              // Prepare data for charts
              const volumeData = allClientMethodsData.methods.map(method => callVolume[method]);
              const executionTimeData = allClientMethodsData.methods.map(method => meanExecutionTime[method]);

              // Call Volume Chart
              clientCallVolumeChartInstance = new Chart("clientCallVolumeChart", {
                  type: 'bar',
                  data: {
                      labels: allClientMethodsData.methods,
                      datasets: [{
                          label: 'Number of Calls',
                          data: volumeData,
                          backgroundColor: 'rgba(255, 107, 107, 0.6)',
                          borderColor: 'rgba(255, 107, 107, 1)',
                          borderWidth: 1,
                          borderRadius: 4
                      }]
                  },
                  options: {
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                          legend: {
                              display: false
                          },
                          tooltip: {
                              backgroundColor: 'rgba(0, 0, 0, 0.8)',
                              padding: 8,
                              titleFont: { size: 12 },
                              bodyFont: { size: 11 },
                              callbacks: {
                                  label: function(context) {
                                      return 'Calls: ' + context.parsed.y;
                                  }
                              }
                          }
                      },
                      scales: {
                          y: {
                              beginAtZero: true,
                              ticks: {
                                  precision: 0
                              }
                          }
                      }
                  }
              });

              // Mean Execution Time Chart
              clientMeanExecutionTimeChartInstance = new Chart("clientMeanExecutionTimeChart", {
                  type: 'bar',
                  data: {
                      labels: allClientMethodsData.methods,
                      datasets: [{
                          label: 'Mean Execution Time (s)',
                          data: executionTimeData,
                          backgroundColor: 'rgba(255, 140, 0, 0.6)',
                          borderColor: 'rgba(255, 140, 0, 1)',
                          borderWidth: 1,
                          borderRadius: 4
                      }]
                  },
                  options: {
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                          legend: {
                              display: false
                          },
                          tooltip: {
                              backgroundColor: 'rgba(0, 0, 0, 0.8)',
                              padding: 8,
                              titleFont: { size: 12 },
                              bodyFont: { size: 11 },
                              callbacks: {
                                  label: function(context) {
                                      return 'Time: ' + context.parsed.y.toFixed(4) + 's';
                                  }
                              }
                          }
                      },
                      scales: {
                          y: {
                              beginAtZero: true,
                              ticks: {
                                  callback: function(value) {
                                      return value.toFixed(4);
                                  }
                              }
                          }
                      }
                  }
              });
          })
          .catch(error => {
              console.error('Error fetching client logs:', error);
              if (clientLogsError) {
                  clientLogsError.style.display = 'block';
              }
              document.getElementById('client-logs-error-text').textContent = 'Failed to load client logs: ' + error.message;
          })
          .finally(() => {
              // Re-enable refresh button
              const refreshBtn = document.getElementById('refreshClientLogsBtn');
              if (refreshBtn) {
                  refreshBtn.disabled = false;
                  refreshBtn.innerHTML = '<i class="mdi mdi-refresh"></i> Refresh Data';
              }
          });
  }

  // Function to update refresh button state based on client selection
  function updateClientRefreshButtonState() {
      const clientSelector = byId('clientSelector');
      const refreshBtn = byId('refreshClientLogsBtn');
      if (!clientSelector || !refreshBtn) return;
      refreshBtn.disabled = !clientSelector.value;
  }

  // Client selector change handler
  bindById('clientSelector', 'change', function() {
      loadClientLogs(this.value);
      updateClientRefreshButtonState();
  });

  // Refresh button click handler for client logs
  const ERROR_MESSAGE_AUTO_HIDE_DELAY = 3000; // milliseconds
  bindById('refreshClientLogsBtn', 'click', function() {
      const clientSelector = byId('clientSelector');
      const errorMessage = byId('client-logs-error-message');
      const errorText = byId('client-logs-error-text');
      const clientId = clientSelector ? clientSelector.value : '';
      if (clientId) {
          loadClientLogs(clientId);
      } else {
          // Show brief feedback that a client must be selected
          if (errorMessage) errorMessage.style.display = 'block';
          if (errorText) errorText.textContent = 'Please select a client first.';
          setTimeout(() => {
              if (errorMessage) errorMessage.style.display = 'none';
          }, ERROR_MESSAGE_AUTO_HIDE_DELAY);
      }
  });

  // Initialize button state on page load
  updateClientRefreshButtonState();

  // Auto-refresh functionality for client logs
  function startClientLogsAutoRefresh() {
      if (clientLogsAutoRefreshInterval) {
          clearInterval(clientLogsAutoRefreshInterval);
      }
      const intervalSeconds = parseInt(document.getElementById('refreshIntervalClientLogs').value) || 30;
      const intervalMs = Math.max(5, Math.min(300, intervalSeconds)) * 1000; // Clamp between 5-300 seconds
      clientLogsAutoRefreshInterval = setInterval(function() {
          const clientId = document.getElementById('clientSelector').value;
          if (clientId) {
              loadClientLogs(clientId);
          }
      }, intervalMs);
  }

  function stopClientLogsAutoRefresh() {
      if (clientLogsAutoRefreshInterval) {
          clearInterval(clientLogsAutoRefreshInterval);
          clientLogsAutoRefreshInterval = null;
      }
  }

  // Auto-refresh checkbox handler
  bindById('autoRefreshClientLogs', 'change', function() {
      if (this.checked) {
          startClientLogsAutoRefresh();
      } else {
          stopClientLogsAutoRefresh();
      }
  });

  // Refresh interval input handler
  bindById('refreshIntervalClientLogs', 'change', function() {
      // Restart auto-refresh with new interval if currently enabled
      const autoRefresh = byId('autoRefreshClientLogs');
      if (autoRefresh && autoRefresh.checked) {
          startClientLogsAutoRefresh();
      }
  });

  // Start auto-refresh if checkbox is checked and client is selected
  if (byId('autoRefreshClientLogs') && byId('autoRefreshClientLogs').checked) {
      startClientLogsAutoRefresh();
  }

  // Select All button handler for methods
  bindById('selectAllMethods', 'click', function() {
      document.querySelectorAll('#methodFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = true;
      });
      updateClientCharts();
  });

  // Deselect All button handler for methods
  bindById('deselectAllMethods', 'click', function() {
      document.querySelectorAll('#methodFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = false;
      });
      updateClientCharts();
  });

  function submitExperimentLogs(expId) {
      const btn = document.getElementById(`submit-logs-btn-${expId}`);
      const messageDiv = document.getElementById(`submit-logs-message-${expId}`);
      const descriptionTextarea = document.getElementById(`problem-description-${expId}`);
    
      // Disable button and show loading
      btn.disabled = true;
      btn.innerHTML = '<span class="icon"><i class="mdi mdi-loading mdi-spin"></i></span><span>Submitting...</span>';
      messageDiv.style.display = 'none';
    
      // Get the problem description
      const problemDescription = descriptionTextarea.value.trim();
    
      // Submit logs with description
      fetch(`/admin/submit_experiment_logs/${expId}`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json'
          },
          body: JSON.stringify({
              problem_description: problemDescription
          })
      })
      .then(response => response.json())
      .then(data => {
          // Show message
          messageDiv.style.display = 'block';
          if (data.success) {
              messageDiv.style.color = '#28a745';
              messageDiv.innerHTML = `<i class="mdi mdi-check-circle"></i> ${data.message}`;
              // Clear the textarea on success
              descriptionTextarea.value = '';
          } else {
              messageDiv.style.color = '#dc3545';
              messageDiv.innerHTML = `<i class="mdi mdi-alert-circle"></i> ${data.message}`;
          }
        
          // Re-enable button
          btn.disabled = false;
          btn.innerHTML = '<span class="icon"><i class="mdi mdi-upload"></i></span><span>Submit Logs</span>';
      })
      .catch(error => {
          messageDiv.style.display = 'block';
          messageDiv.style.color = '#dc3545';
          messageDiv.innerHTML = `<i class="mdi mdi-alert-circle"></i> Error: ${error.message}`;
        
          // Re-enable button
          btn.disabled = false;
          btn.innerHTML = '<span class="icon"><i class="mdi mdi-upload"></i></span><span>Submit Logs</span>';
      });
  }

  function toggleRemoteServerEdit() {
      document.getElementById('remote-display-mode').style.display = 'none';
      document.getElementById('remote-edit-mode').style.display = 'block';
  }

  function cancelRemoteServerEdit() {
      document.getElementById('remote-edit-mode').style.display = 'none';
      document.getElementById('remote-display-mode').style.display = 'block';
  }

  function testRemoteServer() {
      const host = document.getElementById('display-host').textContent;
      const port = document.getElementById('display-port').textContent;
      const statusDiv = document.getElementById('remote-status-message');
    
      statusDiv.innerHTML = '<div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 8px; font-size: 0.85em;"><i class="mdi mdi-loading mdi-spin"></i> Testing connection...</div>';
      statusDiv.style.display = 'block';
    
      const expData = currentExperimentData();
      fetch(`/admin/test_remote_server/${expData.expId}`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
          },
          body: JSON.stringify({ host: host, port: port })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              statusDiv.innerHTML = `<div style="background: #d4edda; border: 1px solid #28a745; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #155724;"><i class="mdi mdi-check-circle"></i> ${data.message}</div>`;
              setTimeout(() => { statusDiv.style.display = 'none'; }, 5000);
          } else {
              statusDiv.innerHTML = `<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> ${data.message}</div>`;
          }
      })
      .catch(error => {
          statusDiv.innerHTML = '<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> Error testing connection</div>';
      });
  }

  function saveRemoteServer() {
      const host = document.getElementById('edit-host').value.trim();
      const port = parseInt(document.getElementById('edit-port').value);
      const statusDiv = document.getElementById('remote-status-message');
    
      if (!host) {
          alert('Please enter a host address');
          return;
      }
    
      if (!port || port < 1 || port > 65535) {
          alert('Please enter a valid port (1-65535)');
          return;
      }
    
      statusDiv.innerHTML = '<div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 8px; font-size: 0.85em;"><i class="mdi mdi-loading mdi-spin"></i> Updating server settings...</div>';
      statusDiv.style.display = 'block';
    
      const expData = currentExperimentData();
      fetch(`/admin/update_remote_server/${expData.expId}`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
          },
          body: JSON.stringify({ host: host, port: port })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              document.getElementById('display-host').textContent = host;
              document.getElementById('display-port').textContent = port;
              cancelRemoteServerEdit();
              statusDiv.innerHTML = '<div style="background: #d4edda; border: 1px solid #28a745; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #155724;"><i class="mdi mdi-check-circle"></i> Server settings updated successfully</div>';
              setTimeout(() => { statusDiv.style.display = 'none'; }, 3000);
          } else {
              statusDiv.innerHTML = `<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> ${data.message}</div>`;
          }
      })
      .catch(error => {
          statusDiv.innerHTML = '<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> Error updating server settings</div>';
      });
  }

  function applyProgressBarState(progressBar, data) {
      if (!progressBar || progressBar.length === 0) {
          return;
      }

      if (data.infinite) {
          progressBar.css('width', '100%');
          progressBar.css('background', 'linear-gradient(90deg, #22c55e 0%, #4ade80 100%)');
          progressBar.css('box-shadow', '0 2px 6px rgba(34,197,94,0.3)');

          const days = data.elapsed_days || 0;
          const hours = data.elapsed_hours || 0;
          const timeText = days > 0 ? (days + 'd ' + hours + 'h') : (hours + 'h elapsed');
          progressBar.find('span').text('∞ ' + timeText);
          return;
      }

      const percentage = Math.min(100, Math.max(0, data.progress || 0));
      progressBar.css('width', percentage + '%');
      progressBar.find('span').text(percentage + '%');

      if (percentage >= 75) {
          progressBar.css('background', 'linear-gradient(90deg, #039be5 0%, #00d1b2 100%)');
          progressBar.css('box-shadow', '0 2px 6px rgba(0,209,178,0.3)');
      } else if (percentage >= 50) {
          progressBar.css('background', 'linear-gradient(90deg, #039be5 0%, #5596e6 100%)');
          progressBar.css('box-shadow', '0 2px 6px rgba(85,150,230,0.3)');
      } else {
          progressBar.css('background', 'linear-gradient(90deg, #039be5 0%, #4facfe 100%)');
          progressBar.css('box-shadow', '0 2px 6px rgba(3,155,229,0.3)');
      }
  }

  function pollAllClientProgress() {
      const progressBars = document.querySelectorAll('.ys-progress-bar[data-progress-url]');
      if (!progressBars.length) {
          return;
      }

      let shouldContinuePolling = false;
      progressBars.forEach((bar) => {
          const progressUrl = bar.dataset.progressUrl;
          if (!progressUrl) {
              return;
          }

          $.ajax({
              url: progressUrl,
              method: 'GET',
              dataType: 'json',
              success: function (data) {
                  applyProgressBarState($(bar), data);
                  if (data.infinite || (data.progress || 0) < 100) {
                      shouldContinuePolling = true;
                  }
              }
          });
      });

      setTimeout(() => {
          const hasActiveBars = Array.from(document.querySelectorAll('.ys-progress-bar[data-progress-url] span'))
              .some((span) => {
                  const text = span.textContent || '';
                  return text.startsWith('∞') || text !== '100%';
              });
          if (shouldContinuePolling || hasActiveBars) {
              pollAllClientProgress();
          }
      }, 1000);
  }

  $(document).ready(function () {
      pollAllClientProgress();
  });

  // Global variables for trend charts
  let serverComputeTimeTrendChart = null;
  let clientComputeTimeTrendChart = null;
  let simulationTimeTrendChart = null;
  let trendsData = {
      daily_compute: {},
      daily_simulation: {},
      hourly_compute: {},
      hourly_simulation: {},
      client_daily_compute: {},
      client_hourly_compute: {}
  };
  let trendsAutoRefreshInterval = null;

  // Function to detect and remove outliers from simulation time data
  function removeOutliers(data) {
      if (data.length < 3) {
          return data; // Not enough data to detect outliers
      }
    
      // Calculate median and MAD (Median Absolute Deviation)
      const sorted = [...data].filter(v => v > 0).sort((a, b) => a - b);
      if (sorted.length === 0) {
          return data;
      }
    
      const median = sorted[Math.floor(sorted.length / 2)];
      const deviations = sorted.map(val => Math.abs(val - median));
      const mad = deviations.sort((a, b) => a - b)[Math.floor(deviations.length / 2)];
    
      // Use modified Z-score with MAD
      // Outliers are values more than 3.5 MAD from the median
      const threshold = 3.5;
      const cleanData = [];
      const validValues = data.filter(v => {
          if (v === 0) return true; // Keep zeros
          const modifiedZScore = Math.abs(0.6745 * (v - median) / (mad || 1));
          return modifiedZScore <= threshold;
      });
    
      // Calculate mean of valid values for replacement
      const validNonZero = validValues.filter(v => v > 0);
      const meanValid = validNonZero.length > 0 
          ? validNonZero.reduce((a, b) => a + b, 0) / validNonZero.length 
          : median;
    
      // Replace outliers with mean of valid values
      return data.map(v => {
          if (v === 0) return v; // Keep zeros
          const modifiedZScore = Math.abs(0.6745 * (v - median) / (mad || 1));
          return modifiedZScore > threshold ? meanValid : v;
      });
  }

  // Function to update trend charts
  function updateTrendCharts() {
      const aggregation = document.querySelector('input[name="aggregation"]:checked').value;
    
      let computeData, simulationData, labels;
      if (aggregation === 'daily') {
          const days = Object.keys(trendsData.daily_compute).sort((a, b) => parseInt(a) - parseInt(b));
          labels = days.map(d => `Day ${d}`);
          computeData = days.map(d => trendsData.daily_compute[d]);
          const rawSimulationData = days.map(d => trendsData.daily_simulation[d] || 0);
          simulationData = removeOutliers(rawSimulationData);
      } else {
          const hours = Object.keys(trendsData.hourly_compute).sort((a, b) => {
              const [dayA, hourA] = a.split('-').map(Number);
              const [dayB, hourB] = b.split('-').map(Number);
              return dayA !== dayB ? dayA - dayB : hourA - hourB;
          });
          labels = hours.map(h => {
              const [day, hour] = h.split('-');
              return `D${day}H${hour}`;
          });
          computeData = hours.map(h => trendsData.hourly_compute[h]);
          const rawSimulationData = hours.map(h => trendsData.hourly_simulation[h] || 0);
          simulationData = removeOutliers(rawSimulationData);
      }

      // Destroy existing server compute time chart before recreating
      if (serverComputeTimeTrendChart) {
          serverComputeTimeTrendChart.destroy();
      }
    
      // Create/recreate server compute time chart
      if (labels.length > 0) {
          serverComputeTimeTrendChart = new Chart('serverComputeTimeTrendChart', {
              type: 'line',
              data: {
                  labels: labels,
                  datasets: [{
                      label: 'Server (s)',
                      data: computeData,
                      borderColor: 'rgba(33, 150, 243, 1)',
                      backgroundColor: 'rgba(33, 150, 243, 0.1)',
                      borderWidth: 2,
                      tension: 0.3,
                      fill: true
                  }]
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: { display: true, position: 'top' }
                  },
                  scales: {
                      y: { beginAtZero: true }
                  }
              }
          });
      }

      // Prepare client compute time datasets
      const clientComputeDatasets = [];
      const clientComputeData = aggregation === 'daily' ? trendsData.client_daily_compute : trendsData.client_hourly_compute;
      if (clientComputeData) {
          const colors = [
              'rgba(255, 99, 132, 1)',
              'rgba(255, 159, 64, 1)',
              'rgba(255, 205, 86, 1)',
              'rgba(75, 192, 192, 1)',
              'rgba(153, 102, 255, 1)',
              'rgba(201, 203, 207, 1)'
          ];
          let colorIndex = 0;

          Object.keys(clientComputeData).forEach(clientName => {
              const clientData = labels.map(label => {
                  // Extract day or day-hour from label
                  let key;
                  if (aggregation === 'daily') {
                      key = parseInt(label.replace('Day ', ''));
                  } else {
                      const match = label.match(/D(\d+)H(\d+)/);
                      if (match) {
                          key = `${match[1]}-${match[2]}`;
                      }
                  }
                  return clientComputeData[clientName][key] || 0;
              });

              const color = colors[colorIndex % colors.length];
              clientComputeDatasets.push({
                  label: `${clientName} (s)`,
                  data: clientData,
                  borderColor: color,
                  backgroundColor: color.replace('1)', '0.1)'),
                  borderWidth: 2,
                  tension: 0.3,
                  fill: false
              });
              colorIndex++;
          });
      }

      // Destroy existing client compute time chart before recreating
      if (clientComputeTimeTrendChart) {
          clientComputeTimeTrendChart.destroy();
      }
    
      // Create/recreate client compute time chart
      if (labels.length > 0 && clientComputeDatasets.length > 0) {
          clientComputeTimeTrendChart = new Chart('clientComputeTimeTrendChart', {
              type: 'line',
              data: {
                  labels: labels,
                  datasets: clientComputeDatasets
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: { display: true, position: 'top' }
                  },
                  scales: {
                      y: { beginAtZero: true }
                  }
              }
          });
      }

      // Destroy existing simulation time chart before recreating
      if (simulationTimeTrendChart) {
          simulationTimeTrendChart.destroy();
      }
    
      // Create/recreate simulation time chart
      if (labels.length > 0) {
          simulationTimeTrendChart = new Chart('simulationTimeTrendChart', {
              type: 'line',
              data: {
                  labels: labels,
                  datasets: [{
                      label: 'Simulation Time (s)',
                      data: simulationData,
                      borderColor: 'rgba(76, 175, 80, 1)',
                      backgroundColor: 'rgba(76, 175, 80, 0.1)',
                      borderWidth: 2,
                      tension: 0.3,
                      fill: true
                  }]
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: { display: true }
                  },
                  scales: {
                      y: { beginAtZero: true }
                  }
              }
          });
      }

      // Update forecast - always locked to daily view
      updateForecast('daily');
  }

  // Function to update forecast
  function updateForecast(aggregation) {
      const computeData = aggregation === 'daily' ? trendsData.daily_compute : trendsData.hourly_compute;
      const rawSimulationData = aggregation === 'daily' ? trendsData.daily_simulation : trendsData.hourly_simulation;
    
      const keys = Object.keys(computeData).sort((a, b) => {
          if (aggregation === 'daily') return parseInt(a) - parseInt(b);
          const [dayA, hourA] = a.split('-').map(Number);
          const [dayB, hourB] = b.split('-').map(Number);
          return dayA !== dayB ? dayA - dayB : hourA - hourB;
      });

      if (keys.length === 0) {
          document.getElementById('forecast-elapsed').textContent = 'No data';
          document.getElementById('forecast-avg-slot').textContent = 'No data';
          document.getElementById('forecast-remaining-slots').textContent = 'No data';
          document.getElementById('forecast-remaining-time').textContent = 'No data';
          return;
      }

      // Apply outlier removal to simulation data for more accurate forecasting
      const rawValues = keys.map(k => rawSimulationData[k] || 0);
      const cleanedValues = removeOutliers(rawValues);
    
      // Calculate total simulation time using cleaned data
      const totalSimulationTime = cleanedValues.reduce((sum, val) => sum + val, 0);
      const completedSlots = keys.length;
      const avgTimePerSlot = totalSimulationTime / completedSlots;

      // Use actual expected duration and remaining time from client_execution table
      // Accounts for clients starting at different times by using max remaining rounds
      // max_remaining_rounds: maximum rounds remaining across all clients (accounts for late starts)
      // total_expected_rounds: maximum expected duration among all clients
      const totalExpectedDays = trendsData.total_expected_days || 0;
      const totalExpectedRounds = trendsData.total_expected_rounds || 0;
      const maxRemainingRounds = trendsData.max_remaining_rounds || 0;
      const maxRemainingDays = trendsData.max_remaining_days || 0;
    
      let totalSlots, remainingSlots;
    
      if (aggregation === 'daily') {
          // Use actual remaining days from the client that has the most work left
          // This accounts for clients starting at different times
          totalSlots = Math.ceil(totalExpectedDays);
          remainingSlots = Math.max(0, Math.ceil(maxRemainingDays));
      } else {
          // Use actual remaining rounds from the client that has the most work left
          // This accounts for clients starting at different times
          totalSlots = totalExpectedRounds;
          remainingSlots = Math.max(0, maxRemainingRounds);
      }

      // If we don't have expected duration from DB, fall back to estimation
      if (totalSlots === 0) {
          const maxKey = keys[keys.length - 1];
          if (aggregation === 'daily') {
              totalSlots = parseInt(maxKey) + 5;
          } else {
              const [maxDay, maxHour] = maxKey.split('-').map(Number);
              totalSlots = (maxDay + 2) * 24;
          }
          remainingSlots = totalSlots - completedSlots;
      }

      const estimatedRemainingTime = avgTimePerSlot * remainingSlots;

      // Format time display
      function formatTime(seconds) {
          const hours = Math.floor(seconds / 3600);
          const minutes = Math.floor((seconds % 3600) / 60);
          const secs = Math.floor(seconds % 60);
          if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
          if (minutes > 0) return `${minutes}m ${secs}s`;
          return `${secs}s`;
      }

      document.getElementById('forecast-elapsed').textContent = formatTime(totalSimulationTime);
      document.getElementById('forecast-avg-slot').textContent = formatTime(avgTimePerSlot);
      document.getElementById('forecast-remaining-slots').textContent = remainingSlots;
      document.getElementById('forecast-remaining-time').textContent = formatTime(estimatedRemainingTime);
  }

  // Function to load trends data
  function loadTrendsData() {
      // Hide error message
      document.getElementById('trends-error-message').style.display = 'none';
    
      // Disable refresh button while loading
      const refreshBtn = document.getElementById('refreshTrendsBtn');
      if (refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Loading...';
      }

      const expData = currentExperimentData();
      if (!expData.expId) {
          return;
      }

      fetch(`/admin/experiment_trends/${expData.expId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  document.getElementById('trends-error-message').style.display = 'block';
                  document.getElementById('trends-error-text').textContent = data.error;
                  return;
              }

              trendsData = data;
              updateTrendCharts();
          })
          .catch(error => {
              console.error('Error fetching trends:', error);
              document.getElementById('trends-error-message').style.display = 'block';
              document.getElementById('trends-error-text').textContent = 'Failed to load trends: ' + error.message;
          })
          .finally(() => {
              // Re-enable refresh button
              if (refreshBtn) {
                  refreshBtn.disabled = false;
                  refreshBtn.innerHTML = '<i class="mdi mdi-refresh"></i> Refresh Data';
              }
          });
  }

  // Load trends data on page load
  loadTrendsData();

  // Auto-refresh functionality
  function startTrendsAutoRefresh() {
      if (trendsAutoRefreshInterval) {
          clearInterval(trendsAutoRefreshInterval);
      }
      const intervalSeconds = parseInt(document.getElementById('refreshIntervalTrends').value) || 30;
      const intervalMs = Math.max(5, Math.min(300, intervalSeconds)) * 1000; // Clamp between 5-300 seconds
      trendsAutoRefreshInterval = setInterval(loadTrendsData, intervalMs);
  }

  function stopTrendsAutoRefresh() {
      if (trendsAutoRefreshInterval) {
          clearInterval(trendsAutoRefreshInterval);
          trendsAutoRefreshInterval = null;
      }
  }

  // Auto-refresh checkbox handler
  bindById('autoRefreshTrends', 'change', function() {
      if (this.checked) {
          startTrendsAutoRefresh();
      } else {
          stopTrendsAutoRefresh();
      }
  });

  // Refresh interval input handler
  bindById('refreshIntervalTrends', 'change', function() {
      // Restart auto-refresh with new interval if currently enabled
      const autoRefresh = byId('autoRefreshTrends');
      if (autoRefresh && autoRefresh.checked) {
          startTrendsAutoRefresh();
      }
  });

  // Start auto-refresh if checkbox is checked
  if (byId('autoRefreshTrends') && byId('autoRefreshTrends').checked) {
      startTrendsAutoRefresh();
  }

  // Refresh button click handler
  bindById('refreshTrendsBtn', 'click', loadTrendsData);

  // Handle aggregation change
  document.querySelectorAll('input[name="aggregation"]').forEach(radio => {
      radio.addEventListener('change', updateTrendCharts);
  });

  // Global variables to store charts and data
  let callVolumeChartInstance = null;
  let meanDurationChartInstance = null;
  let allPathsData = {
      paths: [],
      callVolume: {},
      meanDuration: {}
  };
  let logsAutoRefreshInterval = null;

  // Function to update charts based on selected paths
  function updateCharts() {
      const checkboxes = document.querySelectorAll('#pathFilters input[type="checkbox"]');
      const selectedPaths = [];
    
      checkboxes.forEach(checkbox => {
          if (checkbox.checked) {
              selectedPaths.push(checkbox.value);
          }
      });

      // If no paths selected, show all
      const pathsToShow = selectedPaths.length > 0 ? selectedPaths : allPathsData.paths;
    
      // Prepare filtered data
      const volumeData = pathsToShow.map(path => allPathsData.callVolume[path] || 0);
      const durationData = pathsToShow.map(path => allPathsData.meanDuration[path] || 0);

      // Update Call Volume Chart
      if (callVolumeChartInstance) {
          callVolumeChartInstance.data.labels = pathsToShow;
          callVolumeChartInstance.data.datasets[0].data = volumeData;
          callVolumeChartInstance.update();
      }

      // Update Mean Duration Chart
      if (meanDurationChartInstance) {
          meanDurationChartInstance.data.labels = pathsToShow;
          meanDurationChartInstance.data.datasets[0].data = durationData;
          meanDurationChartInstance.update();
      }
  }

  // Function to create filter checkboxes
  function createPathFilters(paths) {
      const filterContainer = document.getElementById('pathFilters');
      filterContainer.innerHTML = '';
    
      paths.forEach(path => {
          const label = document.createElement('label');
        
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = path;
          checkbox.checked = true;
          checkbox.addEventListener('change', updateCharts);
        
          const span = document.createElement('span');
          span.textContent = path;
        
          label.appendChild(checkbox);
          label.appendChild(span);
          filterContainer.appendChild(label);
      });
  }

  // Select All button handler
  bindById('selectAllPaths', 'click', function() {
      document.querySelectorAll('#pathFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = true;
      });
      updateCharts();
  });

  // Deselect All button handler
  bindById('deselectAllPaths', 'click', function() {
      document.querySelectorAll('#pathFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = false;
      });
      updateCharts();
  });

  // Function to fetch and display server logs data
  function loadServerLogsData() {
      // Hide error message
      document.getElementById('logs-error-message').style.display = 'none';
    
      // Disable refresh button while loading
      const refreshBtn = document.getElementById('refreshLogsBtn');
      if (refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Loading...';
      }

      const expData = currentExperimentData();
      if (!expData.expId) {
          return;
      }

      fetch(`/admin/experiment_logs/${expData.expId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  document.getElementById('logs-error-message').style.display = 'block';
                  document.getElementById('logs-error-text').textContent = data.error;
                  return;
              }

              const callVolume = data.call_volume || {};
              const meanDuration = data.mean_duration || {};

              // Store data globally
              allPathsData.paths = Object.keys(callVolume).sort();
              allPathsData.callVolume = callVolume;
              allPathsData.meanDuration = meanDuration;

              // Create filter checkboxes
              createPathFilters(allPathsData.paths);

              // Prepare data for charts
              const volumeData = allPathsData.paths.map(path => callVolume[path]);
              const durationData = allPathsData.paths.map(path => meanDuration[path]);

              // Destroy existing charts before creating new ones
              if (callVolumeChartInstance) {
                  callVolumeChartInstance.destroy();
              }
              if (meanDurationChartInstance) {
                  meanDurationChartInstance.destroy();
              }

              // Call Volume Chart
              callVolumeChartInstance = new Chart("callVolumeChart", {
                  type: 'bar',
                  data: {
                      labels: allPathsData.paths,
                      datasets: [{
                          label: 'Number of Calls',
                          data: volumeData,
                          backgroundColor: 'rgba(3, 155, 229, 0.6)',
                          borderColor: 'rgba(3, 155, 229, 1)',
                          borderWidth: 1,
                          borderRadius: 4
                      }]
                  },
                  options: {
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                          legend: {
                              display: false
                          },
                          tooltip: {
                              backgroundColor: 'rgba(0, 0, 0, 0.8)',
                              padding: 8,
                              titleFont: { size: 12 },
                              bodyFont: { size: 11 },
                              callbacks: {
                                  label: function(context) {
                                      return 'Calls: ' + context.parsed.y;
                                  }
                              }
                          }
                      },
                      scales: {
                          y: {
                              beginAtZero: true,
                              ticks: {
                                  precision: 0
                              }
                          }
                      }
                  }
              });

              // Mean Duration Chart
              meanDurationChartInstance = new Chart("meanDurationChart", {
              type: 'bar',
              data: {
                  labels: allPathsData.paths,
                  datasets: [{
                      label: 'Mean Duration (s)',
                      data: durationData,
                      backgroundColor: 'rgba(76, 175, 80, 0.6)',
                      borderColor: 'rgba(76, 175, 80, 1)',
                      borderWidth: 1,
                      borderRadius: 4
                  }]
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: {
                          display: false
                      },
                      tooltip: {
                          backgroundColor: 'rgba(0, 0, 0, 0.8)',
                          padding: 8,
                          titleFont: { size: 12 },
                          bodyFont: { size: 11 },
                          callbacks: {
                              label: function(context) {
                                  return 'Duration: ' + context.parsed.y.toFixed(4) + 's';
                              }
                          }
                      }
                  },
                  scales: {
                      y: {
                          beginAtZero: true,
                          ticks: {
                              callback: function(value) {
                                  return value.toFixed(4);
                              }
                          }
                      }
                  }
              }
          });
      })
      .catch(error => {
          console.error('Error fetching logs:', error);
          document.getElementById('logs-error-message').style.display = 'block';
          document.getElementById('logs-error-text').textContent = 'Failed to load server logs: ' + error.message;
      })
      .finally(() => {
          // Re-enable refresh button
          if (refreshBtn) {
              refreshBtn.disabled = false;
              refreshBtn.innerHTML = '<i class="mdi mdi-refresh"></i> Refresh Data';
          }
      });
  }

  // Load server logs data on page load
  loadServerLogsData();

  // Auto-refresh functionality
  function startLogsAutoRefresh() {
      if (logsAutoRefreshInterval) {
          clearInterval(logsAutoRefreshInterval);
      }
      const intervalSeconds = parseInt(document.getElementById('refreshIntervalLogs').value) || 30;
      const intervalMs = Math.max(5, Math.min(300, intervalSeconds)) * 1000; // Clamp between 5-300 seconds
      logsAutoRefreshInterval = setInterval(loadServerLogsData, intervalMs);
  }

  function stopLogsAutoRefresh() {
      if (logsAutoRefreshInterval) {
          clearInterval(logsAutoRefreshInterval);
          logsAutoRefreshInterval = null;
      }
  }

  // Auto-refresh checkbox handler
  bindById('autoRefreshLogs', 'change', function() {
      if (this.checked) {
          startLogsAutoRefresh();
      } else {
          stopLogsAutoRefresh();
      }
  });

  // Refresh interval input handler
  bindById('refreshIntervalLogs', 'change', function() {
      // Restart auto-refresh with new interval if currently enabled
      const autoRefresh = byId('autoRefreshLogs');
      if (autoRefresh && autoRefresh.checked) {
          startLogsAutoRefresh();
      }
  });

  // Start auto-refresh if checkbox is checked
  if (byId('autoRefreshLogs') && byId('autoRefreshLogs').checked) {
      startLogsAutoRefresh();
  }

  // Refresh button click handler
  bindById('refreshLogsBtn', 'click', loadServerLogsData);
})();


/**
 * AdminExperimentsForum - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminExperimentsForum = (function() {
  // Experiment server control functions
  function startExperimentServer(expId) {
      showLoading('Starting experiment server...');
      window.location.href = `/admin/start_experiment/${expId}`;
  }

  function stopExperimentServer(expId) {
      showLoading('Stopping experiment server...');
      window.location.href = `/admin/stop_experiment/${expId}`;
  }

  function selectExperiment(expId) {
      showLoading('Loading experiment interface...');
      window.location.href = `/admin/select_experiment/${expId}`;
  }

  function joinExperiment(expId) {
      showLoading('Joining experiment...');
      window.location.href = `/admin/join_experiment/${expId}`;
  }

  function startJupyter(expId) {
      showLoading('Starting JupyterLab...');
      fetch(`/admin/lab_start/${expId}`)
          .then(response => response.json())
          .then(data => {
              location.reload();
          })
          .catch(error => {
              console.error('Error starting JupyterLab:', error);
              hideLoading();
              showToast('Error starting JupyterLab', 'error');
              setTimeout(() => location.reload(), 1500);
          });
  }

  function stopJupyter(instanceId) {
      showLoading('Stopping JupyterLab...');
      fetch(`/admin/lab_stop/${instanceId}`)
          .then(response => response.json())
          .then(data => {
              location.reload();
          })
          .catch(error => {
              console.error('Error stopping JupyterLab:', error);
              hideLoading();
              showToast('Error stopping JupyterLab', 'error');
              setTimeout(() => location.reload(), 1500);
          });
  }

  // Global variables to store client charts and data
  let clientCallVolumeChartInstance = null;
  let clientMeanExecutionTimeChartInstance = null;
  let allClientMethodsData = {
      methods: [],
      callVolume: {},
      meanExecutionTime: {}
  };
  let clientLogsAutoRefreshInterval = null;

  // Function to update client charts based on selected methods
  function updateClientCharts() {
      const checkboxes = document.querySelectorAll('#methodFilters input[type="checkbox"]');
      const selectedMethods = [];
    
      checkboxes.forEach(checkbox => {
          if (checkbox.checked) {
              selectedMethods.push(checkbox.value);
          }
      });

      // If no methods selected, show all
      const methodsToShow = selectedMethods.length > 0 ? selectedMethods : allClientMethodsData.methods;
    
      // Prepare filtered data
      const volumeData = methodsToShow.map(method => allClientMethodsData.callVolume[method] || 0);
      const executionTimeData = methodsToShow.map(method => allClientMethodsData.meanExecutionTime[method] || 0);

      // Update Call Volume Chart
      if (clientCallVolumeChartInstance) {
          clientCallVolumeChartInstance.data.labels = methodsToShow;
          clientCallVolumeChartInstance.data.datasets[0].data = volumeData;
          clientCallVolumeChartInstance.update();
      }

      // Update Mean Execution Time Chart
      if (clientMeanExecutionTimeChartInstance) {
          clientMeanExecutionTimeChartInstance.data.labels = methodsToShow;
          clientMeanExecutionTimeChartInstance.data.datasets[0].data = executionTimeData;
          clientMeanExecutionTimeChartInstance.update();
      }
  }

  // Function to create method filter checkboxes
  function createMethodFilters(methods) {
      const filterContainer = document.getElementById('methodFilters');
      filterContainer.innerHTML = '';
    
      methods.forEach(method => {
          const label = document.createElement('label');
        
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = method;
          checkbox.checked = true;
          checkbox.addEventListener('change', updateClientCharts);
        
          const span = document.createElement('span');
          span.textContent = method;
        
          label.appendChild(checkbox);
          label.appendChild(span);
          filterContainer.appendChild(label);
      });
  }

  // Function to load client logs
  function loadClientLogs(clientId) {
      // Clear previous data
      if (clientCallVolumeChartInstance) {
          clientCallVolumeChartInstance.destroy();
          clientCallVolumeChartInstance = null;
      }
      if (clientMeanExecutionTimeChartInstance) {
          clientMeanExecutionTimeChartInstance.destroy();
          clientMeanExecutionTimeChartInstance = null;
      }

      // Hide content and error initially
      const clientLogsContent = document.getElementById('client-logs-content');
      const clientLogsError = document.getElementById('client-logs-error-message');
      if (clientLogsContent) {
          clientLogsContent.classList.add('d-none');
          clientLogsContent.style.display = 'none';
      }
      if (clientLogsError) {
          clientLogsError.style.display = 'none';
      }

      if (!clientId) {
          return;
      }

      // Disable refresh button while loading
      const refreshBtn = document.getElementById('refreshClientLogsBtn');
      if (refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Loading...';
      }

      // Fetch and display client logs data
      fetch(`/admin/client_logs/${clientId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  if (clientLogsError) {
                      clientLogsError.style.display = 'block';
                  }
                  document.getElementById('client-logs-error-text').textContent = data.error;
                  return;
              }

              const callVolume = data.call_volume || {};
              const meanExecutionTime = data.mean_execution_time || {};

              // Check if there's any data
              if (Object.keys(callVolume).length === 0) {
                  if (clientLogsError) {
                      clientLogsError.style.display = 'block';
                  }
                  document.getElementById('client-logs-error-text').textContent = 'No log data available for this client.';
                  return;
              }

              // Show content
              if (clientLogsContent) {
                  clientLogsContent.classList.remove('d-none');
                  clientLogsContent.style.display = 'block';
              }

              // Store data globally
              allClientMethodsData.methods = Object.keys(callVolume).sort();
              allClientMethodsData.callVolume = callVolume;
              allClientMethodsData.meanExecutionTime = meanExecutionTime;

              // Create filter checkboxes
              createMethodFilters(allClientMethodsData.methods);

              // Prepare data for charts
              const volumeData = allClientMethodsData.methods.map(method => callVolume[method]);
              const executionTimeData = allClientMethodsData.methods.map(method => meanExecutionTime[method]);

              // Call Volume Chart
              clientCallVolumeChartInstance = new Chart("clientCallVolumeChart", {
                  type: 'bar',
                  data: {
                      labels: allClientMethodsData.methods,
                      datasets: [{
                          label: 'Number of Calls',
                          data: volumeData,
                          backgroundColor: 'rgba(255, 107, 107, 0.6)',
                          borderColor: 'rgba(255, 107, 107, 1)',
                          borderWidth: 1,
                          borderRadius: 4
                      }]
                  },
                  options: {
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                          legend: {
                              display: false
                          },
                          tooltip: {
                              backgroundColor: 'rgba(0, 0, 0, 0.8)',
                              padding: 8,
                              titleFont: { size: 12 },
                              bodyFont: { size: 11 },
                              callbacks: {
                                  label: function(context) {
                                      return 'Calls: ' + context.parsed.y;
                                  }
                              }
                          }
                      },
                      scales: {
                          y: {
                              beginAtZero: true,
                              ticks: {
                                  precision: 0
                              }
                          }
                      }
                  }
              });

              // Mean Execution Time Chart
              clientMeanExecutionTimeChartInstance = new Chart("clientMeanExecutionTimeChart", {
                  type: 'bar',
                  data: {
                      labels: allClientMethodsData.methods,
                      datasets: [{
                          label: 'Mean Execution Time (s)',
                          data: executionTimeData,
                          backgroundColor: 'rgba(255, 140, 0, 0.6)',
                          borderColor: 'rgba(255, 140, 0, 1)',
                          borderWidth: 1,
                          borderRadius: 4
                      }]
                  },
                  options: {
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                          legend: {
                              display: false
                          },
                          tooltip: {
                              backgroundColor: 'rgba(0, 0, 0, 0.8)',
                              padding: 8,
                              titleFont: { size: 12 },
                              bodyFont: { size: 11 },
                              callbacks: {
                                  label: function(context) {
                                      return 'Time: ' + context.parsed.y.toFixed(4) + 's';
                                  }
                              }
                          }
                      },
                      scales: {
                          y: {
                              beginAtZero: true,
                              ticks: {
                                  callback: function(value) {
                                      return value.toFixed(4);
                                  }
                              }
                          }
                      }
                  }
              });
          })
          .catch(error => {
              console.error('Error fetching client logs:', error);
              if (clientLogsError) {
                  clientLogsError.style.display = 'block';
              }
              document.getElementById('client-logs-error-text').textContent = 'Failed to load client logs: ' + error.message;
          })
          .finally(() => {
              // Re-enable refresh button
              const refreshBtn = document.getElementById('refreshClientLogsBtn');
              if (refreshBtn) {
                  refreshBtn.disabled = false;
                  refreshBtn.innerHTML = '<i class="mdi mdi-refresh"></i> Refresh Data';
              }
          });
  }

  // Function to update refresh button state based on client selection
  function updateClientRefreshButtonState() {
      const clientSelector = byId('clientSelector');
      const refreshBtn = byId('refreshClientLogsBtn');
      if (!clientSelector || !refreshBtn) return;
      refreshBtn.disabled = !clientSelector.value;
  }

  // Client selector change handler
  bindById('clientSelector', 'change', function() {
      loadClientLogs(this.value);
      updateClientRefreshButtonState();
  });

  // Refresh button click handler for client logs
  const ERROR_MESSAGE_AUTO_HIDE_DELAY = 3000; // milliseconds
  bindById('refreshClientLogsBtn', 'click', function() {
      const clientSelector = byId('clientSelector');
      const errorMessage = byId('client-logs-error-message');
      const errorText = byId('client-logs-error-text');
      const clientId = clientSelector ? clientSelector.value : '';
      if (clientId) {
          loadClientLogs(clientId);
      } else {
          // Show brief feedback that a client must be selected
          if (errorMessage) errorMessage.style.display = 'block';
          if (errorText) errorText.textContent = 'Please select a client first.';
          setTimeout(() => {
              if (errorMessage) errorMessage.style.display = 'none';
          }, ERROR_MESSAGE_AUTO_HIDE_DELAY);
      }
  });

  // Initialize button state on page load
  updateClientRefreshButtonState();

  // Auto-refresh functionality for client logs
  function startClientLogsAutoRefresh() {
      if (clientLogsAutoRefreshInterval) {
          clearInterval(clientLogsAutoRefreshInterval);
      }
      const intervalSeconds = parseInt(document.getElementById('refreshIntervalClientLogs').value) || 30;
      const intervalMs = Math.max(5, Math.min(300, intervalSeconds)) * 1000; // Clamp between 5-300 seconds
      clientLogsAutoRefreshInterval = setInterval(function() {
          const clientId = document.getElementById('clientSelector').value;
          if (clientId) {
              loadClientLogs(clientId);
          }
      }, intervalMs);
  }

  function stopClientLogsAutoRefresh() {
      if (clientLogsAutoRefreshInterval) {
          clearInterval(clientLogsAutoRefreshInterval);
          clientLogsAutoRefreshInterval = null;
      }
  }

  // Auto-refresh checkbox handler
  bindById('autoRefreshClientLogs', 'change', function() {
      if (this.checked) {
          startClientLogsAutoRefresh();
      } else {
          stopClientLogsAutoRefresh();
      }
  });

  // Refresh interval input handler
  bindById('refreshIntervalClientLogs', 'change', function() {
      // Restart auto-refresh with new interval if currently enabled
      const autoRefresh = byId('autoRefreshClientLogs');
      if (autoRefresh && autoRefresh.checked) {
          startClientLogsAutoRefresh();
      }
  });

  // Start auto-refresh if checkbox is checked and client is selected
  if (byId('autoRefreshClientLogs') && byId('autoRefreshClientLogs').checked) {
      startClientLogsAutoRefresh();
  }

  // Select All button handler for methods
  bindById('selectAllMethods', 'click', function() {
      document.querySelectorAll('#methodFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = true;
      });
      updateClientCharts();
  });

  // Deselect All button handler for methods
  bindById('deselectAllMethods', 'click', function() {
      document.querySelectorAll('#methodFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = false;
      });
      updateClientCharts();
  });

  function submitExperimentLogs(expId) {
      const btn = document.getElementById(`submit-logs-btn-${expId}`);
      const messageDiv = document.getElementById(`submit-logs-message-${expId}`);
      const descriptionTextarea = document.getElementById(`problem-description-${expId}`);
    
      // Disable button and show loading
      btn.disabled = true;
      btn.innerHTML = '<span class="icon"><i class="mdi mdi-loading mdi-spin"></i></span><span>Submitting...</span>';
      messageDiv.style.display = 'none';
    
      // Get the problem description
      const problemDescription = descriptionTextarea.value.trim();
    
      // Submit logs with description
      fetch(`/admin/submit_experiment_logs/${expId}`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json'
          },
          body: JSON.stringify({
              problem_description: problemDescription
          })
      })
      .then(response => response.json())
      .then(data => {
          // Show message
          messageDiv.style.display = 'block';
          if (data.success) {
              messageDiv.style.color = '#28a745';
              messageDiv.innerHTML = `<i class="mdi mdi-check-circle"></i> ${data.message}`;
              // Clear the textarea on success
              descriptionTextarea.value = '';
          } else {
              messageDiv.style.color = '#dc3545';
              messageDiv.innerHTML = `<i class="mdi mdi-alert-circle"></i> ${data.message}`;
          }
        
          // Re-enable button
          btn.disabled = false;
          btn.innerHTML = '<span class="icon"><i class="mdi mdi-upload"></i></span><span>Submit Logs</span>';
      })
      .catch(error => {
          messageDiv.style.display = 'block';
          messageDiv.style.color = '#dc3545';
          messageDiv.innerHTML = `<i class="mdi mdi-alert-circle"></i> Error: ${error.message}`;
        
          // Re-enable button
          btn.disabled = false;
          btn.innerHTML = '<span class="icon"><i class="mdi mdi-upload"></i></span><span>Submit Logs</span>';
      });
  }

  function toggleRemoteServerEdit() {
      document.getElementById('remote-display-mode').style.display = 'none';
      document.getElementById('remote-edit-mode').style.display = 'block';
  }

  function cancelRemoteServerEdit() {
      document.getElementById('remote-edit-mode').style.display = 'none';
      document.getElementById('remote-display-mode').style.display = 'block';
  }

  function testRemoteServer() {
      const host = document.getElementById('display-host').textContent;
      const port = document.getElementById('display-port').textContent;
      const statusDiv = document.getElementById('remote-status-message');
    
      statusDiv.innerHTML = '<div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 8px; font-size: 0.85em;"><i class="mdi mdi-loading mdi-spin"></i> Testing connection...</div>';
      statusDiv.style.display = 'block';
    
      const expData = currentExperimentData();
      fetch(`/admin/test_remote_server/${expData.expId}`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
          },
          body: JSON.stringify({ host: host, port: port })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              statusDiv.innerHTML = `<div style="background: #d4edda; border: 1px solid #28a745; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #155724;"><i class="mdi mdi-check-circle"></i> ${data.message}</div>`;
              setTimeout(() => { statusDiv.style.display = 'none'; }, 5000);
          } else {
              statusDiv.innerHTML = `<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> ${data.message}</div>`;
          }
      })
      .catch(error => {
          statusDiv.innerHTML = '<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> Error testing connection</div>';
      });
  }

  function saveRemoteServer() {
      const host = document.getElementById('edit-host').value.trim();
      const port = parseInt(document.getElementById('edit-port').value);
      const statusDiv = document.getElementById('remote-status-message');
    
      if (!host) {
          alert('Please enter a host address');
          return;
      }
    
      if (!port || port < 1 || port > 65535) {
          alert('Please enter a valid port (1-65535)');
          return;
      }
    
      statusDiv.innerHTML = '<div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 8px; font-size: 0.85em;"><i class="mdi mdi-loading mdi-spin"></i> Updating server settings...</div>';
      statusDiv.style.display = 'block';
    
      const expData = currentExperimentData();
      fetch(`/admin/update_remote_server/${expData.expId}`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
          },
          body: JSON.stringify({ host: host, port: port })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              document.getElementById('display-host').textContent = host;
              document.getElementById('display-port').textContent = port;
              cancelRemoteServerEdit();
              statusDiv.innerHTML = '<div style="background: #d4edda; border: 1px solid #28a745; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #155724;"><i class="mdi mdi-check-circle"></i> Server settings updated successfully</div>';
              setTimeout(() => { statusDiv.style.display = 'none'; }, 3000);
          } else {
              statusDiv.innerHTML = `<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> ${data.message}</div>`;
          }
      })
      .catch(error => {
          statusDiv.innerHTML = '<div style="background: #f8d7da; border: 1px solid #dc3545; border-radius: 4px; padding: 8px; font-size: 0.85em; color: #721c24;"><i class="mdi mdi-alert-circle"></i> Error updating server settings</div>';
      });
  }

  // Global variables for trend charts
  let serverComputeTimeTrendChart = null;
  let clientComputeTimeTrendChart = null;
  let simulationTimeTrendChart = null;
  let trendsData = {
      daily_compute: {},
      daily_simulation: {},
      hourly_compute: {},
      hourly_simulation: {},
      client_daily_compute: {},
      client_hourly_compute: {}
  };
  let trendsAutoRefreshInterval = null;

  // Function to detect and remove outliers from simulation time data
  function removeOutliers(data) {
      if (data.length < 3) {
          return data; // Not enough data to detect outliers
      }
    
      // Calculate median and MAD (Median Absolute Deviation)
      const sorted = [...data].filter(v => v > 0).sort((a, b) => a - b);
      if (sorted.length === 0) {
          return data;
      }
    
      const median = sorted[Math.floor(sorted.length / 2)];
      const deviations = sorted.map(val => Math.abs(val - median));
      const mad = deviations.sort((a, b) => a - b)[Math.floor(deviations.length / 2)];
    
      // Use modified Z-score with MAD
      // Outliers are values more than 3.5 MAD from the median
      const threshold = 3.5;
      const cleanData = [];
      const validValues = data.filter(v => {
          if (v === 0) return true; // Keep zeros
          const modifiedZScore = Math.abs(0.6745 * (v - median) / (mad || 1));
          return modifiedZScore <= threshold;
      });
    
      // Calculate mean of valid values for replacement
      const validNonZero = validValues.filter(v => v > 0);
      const meanValid = validNonZero.length > 0 
          ? validNonZero.reduce((a, b) => a + b, 0) / validNonZero.length 
          : median;
    
      // Replace outliers with mean of valid values
      return data.map(v => {
          if (v === 0) return v; // Keep zeros
          const modifiedZScore = Math.abs(0.6745 * (v - median) / (mad || 1));
          return modifiedZScore > threshold ? meanValid : v;
      });
  }

  // Function to update trend charts
  function updateTrendCharts() {
      const aggregation = document.querySelector('input[name="aggregation"]:checked').value;
    
      let computeData, simulationData, labels;
      if (aggregation === 'daily') {
          const days = Object.keys(trendsData.daily_compute).sort((a, b) => parseInt(a) - parseInt(b));
          labels = days.map(d => `Day ${d}`);
          computeData = days.map(d => trendsData.daily_compute[d]);
          const rawSimulationData = days.map(d => trendsData.daily_simulation[d] || 0);
          simulationData = removeOutliers(rawSimulationData);
      } else {
          const hours = Object.keys(trendsData.hourly_compute).sort((a, b) => {
              const [dayA, hourA] = a.split('-').map(Number);
              const [dayB, hourB] = b.split('-').map(Number);
              return dayA !== dayB ? dayA - dayB : hourA - hourB;
          });
          labels = hours.map(h => {
              const [day, hour] = h.split('-');
              return `D${day}H${hour}`;
          });
          computeData = hours.map(h => trendsData.hourly_compute[h]);
          const rawSimulationData = hours.map(h => trendsData.hourly_simulation[h] || 0);
          simulationData = removeOutliers(rawSimulationData);
      }

      // Destroy existing server compute time chart before recreating
      if (serverComputeTimeTrendChart) {
          serverComputeTimeTrendChart.destroy();
      }
    
      // Create/recreate server compute time chart
      if (labels.length > 0) {
          serverComputeTimeTrendChart = new Chart('serverComputeTimeTrendChart', {
              type: 'line',
              data: {
                  labels: labels,
                  datasets: [{
                      label: 'Server (s)',
                      data: computeData,
                      borderColor: 'rgba(33, 150, 243, 1)',
                      backgroundColor: 'rgba(33, 150, 243, 0.1)',
                      borderWidth: 2,
                      tension: 0.3,
                      fill: true
                  }]
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: { display: true, position: 'top' }
                  },
                  scales: {
                      y: { beginAtZero: true }
                  }
              }
          });
      }

      // Prepare client compute time datasets
      const clientComputeDatasets = [];
      const clientComputeData = aggregation === 'daily' ? trendsData.client_daily_compute : trendsData.client_hourly_compute;
      if (clientComputeData) {
          const colors = [
              'rgba(255, 99, 132, 1)',
              'rgba(255, 159, 64, 1)',
              'rgba(255, 205, 86, 1)',
              'rgba(75, 192, 192, 1)',
              'rgba(153, 102, 255, 1)',
              'rgba(201, 203, 207, 1)'
          ];
          let colorIndex = 0;

          Object.keys(clientComputeData).forEach(clientName => {
              const clientData = labels.map(label => {
                  // Extract day or day-hour from label
                  let key;
                  if (aggregation === 'daily') {
                      key = parseInt(label.replace('Day ', ''));
                  } else {
                      const match = label.match(/D(\d+)H(\d+)/);
                      if (match) {
                          key = `${match[1]}-${match[2]}`;
                      }
                  }
                  return clientComputeData[clientName][key] || 0;
              });

              const color = colors[colorIndex % colors.length];
              clientComputeDatasets.push({
                  label: `${clientName} (s)`,
                  data: clientData,
                  borderColor: color,
                  backgroundColor: color.replace('1)', '0.1)'),
                  borderWidth: 2,
                  tension: 0.3,
                  fill: false
              });
              colorIndex++;
          });
      }

      // Destroy existing client compute time chart before recreating
      if (clientComputeTimeTrendChart) {
          clientComputeTimeTrendChart.destroy();
      }
    
      // Create/recreate client compute time chart
      if (labels.length > 0 && clientComputeDatasets.length > 0) {
          clientComputeTimeTrendChart = new Chart('clientComputeTimeTrendChart', {
              type: 'line',
              data: {
                  labels: labels,
                  datasets: clientComputeDatasets
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: { display: true, position: 'top' }
                  },
                  scales: {
                      y: { beginAtZero: true }
                  }
              }
          });
      }

      // Destroy existing simulation time chart before recreating
      if (simulationTimeTrendChart) {
          simulationTimeTrendChart.destroy();
      }
    
      // Create/recreate simulation time chart
      if (labels.length > 0) {
          simulationTimeTrendChart = new Chart('simulationTimeTrendChart', {
              type: 'line',
              data: {
                  labels: labels,
                  datasets: [{
                      label: 'Simulation Time (s)',
                      data: simulationData,
                      borderColor: 'rgba(76, 175, 80, 1)',
                      backgroundColor: 'rgba(76, 175, 80, 0.1)',
                      borderWidth: 2,
                      tension: 0.3,
                      fill: true
                  }]
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: { display: true }
                  },
                  scales: {
                      y: { beginAtZero: true }
                  }
              }
          });
      }

      // Update forecast - always locked to daily view
      updateForecast('daily');
  }

  // Function to update forecast
  function updateForecast(aggregation) {
      const computeData = aggregation === 'daily' ? trendsData.daily_compute : trendsData.hourly_compute;
      const rawSimulationData = aggregation === 'daily' ? trendsData.daily_simulation : trendsData.hourly_simulation;
    
      const keys = Object.keys(computeData).sort((a, b) => {
          if (aggregation === 'daily') return parseInt(a) - parseInt(b);
          const [dayA, hourA] = a.split('-').map(Number);
          const [dayB, hourB] = b.split('-').map(Number);
          return dayA !== dayB ? dayA - dayB : hourA - hourB;
      });

      if (keys.length === 0) {
          document.getElementById('forecast-elapsed').textContent = 'No data';
          document.getElementById('forecast-avg-slot').textContent = 'No data';
          document.getElementById('forecast-remaining-slots').textContent = 'No data';
          document.getElementById('forecast-remaining-time').textContent = 'No data';
          return;
      }

      // Apply outlier removal to simulation data for more accurate forecasting
      const rawValues = keys.map(k => rawSimulationData[k] || 0);
      const cleanedValues = removeOutliers(rawValues);
    
      // Calculate total simulation time using cleaned data
      const totalSimulationTime = cleanedValues.reduce((sum, val) => sum + val, 0);
      const completedSlots = keys.length;
      const avgTimePerSlot = totalSimulationTime / completedSlots;

      // Use actual expected duration and remaining time from client_execution table
      // Accounts for clients starting at different times by using max remaining rounds
      // max_remaining_rounds: maximum rounds remaining across all clients (accounts for late starts)
      // total_expected_rounds: maximum expected duration among all clients
      const totalExpectedDays = trendsData.total_expected_days || 0;
      const totalExpectedRounds = trendsData.total_expected_rounds || 0;
      const maxRemainingRounds = trendsData.max_remaining_rounds || 0;
      const maxRemainingDays = trendsData.max_remaining_days || 0;
    
      let totalSlots, remainingSlots;
    
      if (aggregation === 'daily') {
          // Use actual remaining days from the client that has the most work left
          // This accounts for clients starting at different times
          totalSlots = Math.ceil(totalExpectedDays);
          remainingSlots = Math.max(0, Math.ceil(maxRemainingDays));
      } else {
          // Use actual remaining rounds from the client that has the most work left
          // This accounts for clients starting at different times
          totalSlots = totalExpectedRounds;
          remainingSlots = Math.max(0, maxRemainingRounds);
      }

      // If we don't have expected duration from DB, fall back to estimation
      if (totalSlots === 0) {
          const maxKey = keys[keys.length - 1];
          if (aggregation === 'daily') {
              totalSlots = parseInt(maxKey) + 5;
          } else {
              const [maxDay, maxHour] = maxKey.split('-').map(Number);
              totalSlots = (maxDay + 2) * 24;
          }
          remainingSlots = totalSlots - completedSlots;
      }

      const estimatedRemainingTime = avgTimePerSlot * remainingSlots;

      // Format time display
      function formatTime(seconds) {
          const hours = Math.floor(seconds / 3600);
          const minutes = Math.floor((seconds % 3600) / 60);
          const secs = Math.floor(seconds % 60);
          if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
          if (minutes > 0) return `${minutes}m ${secs}s`;
          return `${secs}s`;
      }

      document.getElementById('forecast-elapsed').textContent = formatTime(totalSimulationTime);
      document.getElementById('forecast-avg-slot').textContent = formatTime(avgTimePerSlot);
      document.getElementById('forecast-remaining-slots').textContent = remainingSlots;
      document.getElementById('forecast-remaining-time').textContent = formatTime(estimatedRemainingTime);
  }

  // Function to load trends data
  function loadTrendsData() {
      // Hide error message
      document.getElementById('trends-error-message').style.display = 'none';
    
      // Disable refresh button while loading
      const refreshBtn = document.getElementById('refreshTrendsBtn');
      if (refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Loading...';
      }

      const expData = currentExperimentData();
      if (!expData.expId) {
          return;
      }

      fetch(`/admin/experiment_trends/${expData.expId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  document.getElementById('trends-error-message').style.display = 'block';
                  document.getElementById('trends-error-text').textContent = data.error;
                  return;
              }

              trendsData = data;
              updateTrendCharts();
          })
          .catch(error => {
              console.error('Error fetching trends:', error);
              document.getElementById('trends-error-message').style.display = 'block';
              document.getElementById('trends-error-text').textContent = 'Failed to load trends: ' + error.message;
          })
          .finally(() => {
              // Re-enable refresh button
              if (refreshBtn) {
                  refreshBtn.disabled = false;
                  refreshBtn.innerHTML = '<i class="mdi mdi-refresh"></i> Refresh Data';
              }
          });
  }

  // Load trends data on page load
  loadTrendsData();

  // Auto-refresh functionality
  function startTrendsAutoRefresh() {
      if (trendsAutoRefreshInterval) {
          clearInterval(trendsAutoRefreshInterval);
      }
      const intervalSeconds = parseInt(document.getElementById('refreshIntervalTrends').value) || 30;
      const intervalMs = Math.max(5, Math.min(300, intervalSeconds)) * 1000; // Clamp between 5-300 seconds
      trendsAutoRefreshInterval = setInterval(loadTrendsData, intervalMs);
  }

  function stopTrendsAutoRefresh() {
      if (trendsAutoRefreshInterval) {
          clearInterval(trendsAutoRefreshInterval);
          trendsAutoRefreshInterval = null;
      }
  }

  // Auto-refresh checkbox handler
  bindById('autoRefreshTrends', 'change', function() {
      if (this.checked) {
          startTrendsAutoRefresh();
      } else {
          stopTrendsAutoRefresh();
      }
  });

  // Refresh interval input handler
  bindById('refreshIntervalTrends', 'change', function() {
      // Restart auto-refresh with new interval if currently enabled
      const autoRefresh = byId('autoRefreshTrends');
      if (autoRefresh && autoRefresh.checked) {
          startTrendsAutoRefresh();
      }
  });

  // Start auto-refresh if checkbox is checked
  if (byId('autoRefreshTrends') && byId('autoRefreshTrends').checked) {
      startTrendsAutoRefresh();
  }

  // Refresh button click handler
  bindById('refreshTrendsBtn', 'click', loadTrendsData);

  // Handle aggregation change
  document.querySelectorAll('input[name="aggregation"]').forEach(radio => {
      radio.addEventListener('change', updateTrendCharts);
  });

  // Global variables to store charts and data
  let callVolumeChartInstance = null;
  let meanDurationChartInstance = null;
  let allPathsData = {
      paths: [],
      callVolume: {},
      meanDuration: {}
  };
  let logsAutoRefreshInterval = null;

  // Function to update charts based on selected paths
  function updateCharts() {
      const checkboxes = document.querySelectorAll('#pathFilters input[type="checkbox"]');
      const selectedPaths = [];
    
      checkboxes.forEach(checkbox => {
          if (checkbox.checked) {
              selectedPaths.push(checkbox.value);
          }
      });

      // If no paths selected, show all
      const pathsToShow = selectedPaths.length > 0 ? selectedPaths : allPathsData.paths;
    
      // Prepare filtered data
      const volumeData = pathsToShow.map(path => allPathsData.callVolume[path] || 0);
      const durationData = pathsToShow.map(path => allPathsData.meanDuration[path] || 0);

      // Update Call Volume Chart
      if (callVolumeChartInstance) {
          callVolumeChartInstance.data.labels = pathsToShow;
          callVolumeChartInstance.data.datasets[0].data = volumeData;
          callVolumeChartInstance.update();
      }

      // Update Mean Duration Chart
      if (meanDurationChartInstance) {
          meanDurationChartInstance.data.labels = pathsToShow;
          meanDurationChartInstance.data.datasets[0].data = durationData;
          meanDurationChartInstance.update();
      }
  }

  // Function to create filter checkboxes
  function createPathFilters(paths) {
      const filterContainer = document.getElementById('pathFilters');
      filterContainer.innerHTML = '';
    
      paths.forEach(path => {
          const label = document.createElement('label');
        
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = path;
          checkbox.checked = true;
          checkbox.addEventListener('change', updateCharts);
        
          const span = document.createElement('span');
          span.textContent = path;
        
          label.appendChild(checkbox);
          label.appendChild(span);
          filterContainer.appendChild(label);
      });
  }

  // Select All button handler
  bindById('selectAllPaths', 'click', function() {
      document.querySelectorAll('#pathFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = true;
      });
      updateCharts();
  });

  // Deselect All button handler
  bindById('deselectAllPaths', 'click', function() {
      document.querySelectorAll('#pathFilters input[type="checkbox"]').forEach(checkbox => {
          checkbox.checked = false;
      });
      updateCharts();
  });

  // Function to fetch and display server logs data
  function loadServerLogsData() {
      // Hide error message
      document.getElementById('logs-error-message').style.display = 'none';
    
      // Disable refresh button while loading
      const refreshBtn = document.getElementById('refreshLogsBtn');
      if (refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Loading...';
      }

      const expData = currentExperimentData();
      if (!expData.expId) {
          return;
      }

      fetch(`/admin/experiment_logs/${expData.expId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  document.getElementById('logs-error-message').style.display = 'block';
                  document.getElementById('logs-error-text').textContent = data.error;
                  return;
              }

              const callVolume = data.call_volume || {};
              const meanDuration = data.mean_duration || {};

              // Store data globally
              allPathsData.paths = Object.keys(callVolume).sort();
              allPathsData.callVolume = callVolume;
              allPathsData.meanDuration = meanDuration;

              // Create filter checkboxes
              createPathFilters(allPathsData.paths);

              // Prepare data for charts
              const volumeData = allPathsData.paths.map(path => callVolume[path]);
              const durationData = allPathsData.paths.map(path => meanDuration[path]);

              // Destroy existing charts before creating new ones
              if (callVolumeChartInstance) {
                  callVolumeChartInstance.destroy();
              }
              if (meanDurationChartInstance) {
                  meanDurationChartInstance.destroy();
              }

              // Call Volume Chart
              callVolumeChartInstance = new Chart("callVolumeChart", {
                  type: 'bar',
                  data: {
                      labels: allPathsData.paths,
                      datasets: [{
                          label: 'Number of Calls',
                          data: volumeData,
                          backgroundColor: 'rgba(3, 155, 229, 0.6)',
                          borderColor: 'rgba(3, 155, 229, 1)',
                          borderWidth: 1,
                          borderRadius: 4
                      }]
                  },
                  options: {
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                          legend: {
                              display: false
                          },
                          tooltip: {
                              backgroundColor: 'rgba(0, 0, 0, 0.8)',
                              padding: 8,
                              titleFont: { size: 12 },
                              bodyFont: { size: 11 },
                              callbacks: {
                                  label: function(context) {
                                      return 'Calls: ' + context.parsed.y;
                                  }
                              }
                          }
                      },
                      scales: {
                          y: {
                              beginAtZero: true,
                              ticks: {
                                  precision: 0
                              }
                          }
                      }
                  }
              });

              // Mean Duration Chart
              meanDurationChartInstance = new Chart("meanDurationChart", {
              type: 'bar',
              data: {
                  labels: allPathsData.paths,
                  datasets: [{
                      label: 'Mean Duration (s)',
                      data: durationData,
                      backgroundColor: 'rgba(76, 175, 80, 0.6)',
                      borderColor: 'rgba(76, 175, 80, 1)',
                      borderWidth: 1,
                      borderRadius: 4
                  }]
              },
              options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                      legend: {
                          display: false
                      },
                      tooltip: {
                          backgroundColor: 'rgba(0, 0, 0, 0.8)',
                          padding: 8,
                          titleFont: { size: 12 },
                          bodyFont: { size: 11 },
                          callbacks: {
                              label: function(context) {
                                  return 'Duration: ' + context.parsed.y.toFixed(4) + 's';
                              }
                          }
                      }
                  },
                  scales: {
                      y: {
                          beginAtZero: true,
                          ticks: {
                              callback: function(value) {
                                  return value.toFixed(4);
                              }
                          }
                      }
                  }
              }
          });
      })
      .catch(error => {
          console.error('Error fetching logs:', error);
          document.getElementById('logs-error-message').style.display = 'block';
          document.getElementById('logs-error-text').textContent = 'Failed to load server logs: ' + error.message;
      })
      .finally(() => {
          // Re-enable refresh button
          if (refreshBtn) {
              refreshBtn.disabled = false;
              refreshBtn.innerHTML = '<i class="mdi mdi-refresh"></i> Refresh Data';
          }
      });
  }

  // Load server logs data on page load
  loadServerLogsData();

  // Auto-refresh functionality
  function startLogsAutoRefresh() {
      if (logsAutoRefreshInterval) {
          clearInterval(logsAutoRefreshInterval);
      }
      const intervalSeconds = parseInt(document.getElementById('refreshIntervalLogs').value) || 30;
      const intervalMs = Math.max(5, Math.min(300, intervalSeconds)) * 1000; // Clamp between 5-300 seconds
      logsAutoRefreshInterval = setInterval(loadServerLogsData, intervalMs);
  }

  function stopLogsAutoRefresh() {
      if (logsAutoRefreshInterval) {
          clearInterval(logsAutoRefreshInterval);
          logsAutoRefreshInterval = null;
      }
  }

  // Auto-refresh checkbox handler
  bindById('autoRefreshLogs', 'change', function() {
      if (this.checked) {
          startLogsAutoRefresh();
      } else {
          stopLogsAutoRefresh();
      }
  });

  // Refresh interval input handler
  bindById('refreshIntervalLogs', 'change', function() {
      // Restart auto-refresh with new interval if currently enabled
      const autoRefresh = byId('autoRefreshLogs');
      if (autoRefresh && autoRefresh.checked) {
          startLogsAutoRefresh();
      }
  });

  // Start auto-refresh if checkbox is checked
  if (byId('autoRefreshLogs') && byId('autoRefreshLogs').checked) {
      startLogsAutoRefresh();
  }

  // Refresh button click handler
  bindById('refreshLogsBtn', 'click', loadServerLogsData);

  Object.assign(window, {
      startExperimentServer,
      stopExperimentServer,
      selectExperiment,
      joinExperiment,
      startJupyter,
      stopJupyter,
      submitExperimentLogs,
      toggleRemoteServerEdit,
      cancelRemoteServerEdit,
      testRemoteServer,
      saveRemoteServer
  });
})();
