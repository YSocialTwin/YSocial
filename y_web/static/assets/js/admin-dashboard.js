/**
 * AdminDashboard - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminDashboard = (function() {
  function dismissTelemetryNotice() {
      fetch('/admin/dismiss_telemetry_notice', {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
          }
      }).then(() => {
          document.getElementById('telemetry-overlay').style.display = 'none';
      });
  }

  // Toggle group fold/unfold functionality
  function toggleGroup(groupId) {
      const content = document.getElementById(groupId);
      const icon = document.getElementById('icon-' + groupId);
    
      if (content.style.display === 'none') {
          content.style.display = 'block';
          icon.style.transform = 'rotate(0deg)';
      } else {
          content.style.display = 'none';
          icon.style.transform = 'rotate(-90deg)';
      }
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
      const progressBars = document.querySelectorAll('[id^="progress-bar-"]');
      if (!progressBars.length) {
          return;
      }

      let shouldContinuePolling = false;
      progressBars.forEach((bar) => {
          const clientId = bar.id.replace('progress-bar-', '');
          if (!clientId) {
              return;
          }

          $.ajax({
              url: `/admin/progress/${clientId}`,
              method: 'GET',
              dataType: 'json',
              success: function (data) {
                  applyProgressBarState($(`#progress-bar-${clientId}`), data);
                  if (data.infinite || (data.progress || 0) < 100) {
                      shouldContinuePolling = true;
                  }
              }
          });
      });

      setTimeout(() => {
          const hasActiveBars = Array.from(document.querySelectorAll('[id^="progress-bar-"] span'))
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

  function startJupyterSession(expId) {
      fetch(`/admin/lab_start/${expId}`)
          .then(response => response.json())
          .then(data => {
              location.reload();
          })
          .catch(error => {
              console.error('Error starting JupyterLab:', error);
              location.reload();
          });
  }

  function stopJupyterSession(expId) {
      fetch(`/admin/lab_stop/${expId}`)
          .then(response => response.json())
          .then(data => {
              location.reload();
          })
          .catch(error => {
              console.error('Error stopping JupyterLab:', error);
              location.reload();
          });
  }

  // Dynamic dashboard refresh - update experiment status every 30 seconds
  const DASHBOARD_REFRESH_INTERVAL = 30000;

  // Track current counts to detect changes
  let dashboardState = {
      running: YS_DATA_DASHBOARD.totalRunning,
      completed: YS_DATA_DASHBOARD.totalCompleted,
      stopped: YS_DATA_DASHBOARD.totalStopped
  };

  // Check if tutorial overlay is open
  function isTutorialOpen() {
      const overlay = document.getElementById('tutorial-overlay');
      return overlay && overlay.style.display !== 'none';
  }

  // Async refresh of experiment containers
  async function refreshDashboardAsync() {
      // Don't refresh if tutorial is open
      if (isTutorialOpen()) {
          console.log('Tutorial is open, skipping dashboard refresh');
          return;
      }
    
      try {
          // Fetch current status
          const statusResponse = await fetch('/admin/dashboard/status');
          const statusData = await statusResponse.json();
        
          // Update counts in headers if they changed
          if (statusData.running !== dashboardState.running ||
              statusData.completed !== dashboardState.completed ||
              statusData.stopped !== dashboardState.stopped) {
            
              // Update state
              dashboardState.running = statusData.running;
              dashboardState.completed = statusData.completed;
              dashboardState.stopped = statusData.stopped;
            
              // Fetch updated experiment data for each section
              await Promise.all([
                  refreshExperimentSection('running', '#28a745'),
                  refreshExperimentSection('completed', '#17a2b8'),
                  refreshExperimentSection('stopped', '#6c757d')
              ]);
          }
      } catch (error) {
          console.error('Error refreshing dashboard:', error);
      }
  }

  async function refreshExperimentSection(status, sectionColor) {
      try {
          const response = await fetch(`/admin/dashboard/experiments/${status}?page=1&per_page=5`);
          const data = await response.json();
        
          const containerId = `${status === 'running' ? 'running' : status}-experiments-container`;
          const container = document.getElementById(containerId);
        
          if (container && data.experiments) {
              // Use compact rendering for completed/stopped, full for running
              const renderFunc = status === 'running' 
                  ? (exp) => renderExperimentBoxFromData(exp, sectionColor, {}, false, false)
                  : (exp) => renderCompactExperimentBoxFromData(exp, sectionColor);
              const html = data.experiments.map(renderFunc).join('');
              container.innerHTML = html || '<p style="color: #666; text-align: center;">No experiments in this category</p>';
          }
      } catch (error) {
          console.error(`Error refreshing ${status} experiments:`, error);
      }
  }

  // Start periodic async refresh
  setInterval(refreshDashboardAsync, DASHBOARD_REFRESH_INTERVAL);

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

  // Render a compact experiment box from JSON data (for completed/stopped)
  function renderCompactExperimentBoxFromData(exp, sectionColor) {
      const hasInfiniteClient = exp.clients.some(client => client.days === -1);
      const clientCount = exp.clients.length;
      const expStatus = exp.exp_status || '';
      const hasStartedOnce = Boolean(exp.has_started_once);
      const expProgress = typeof exp.progress === 'number' ? exp.progress : null;
      const progressLabel = typeof exp.progress_label === 'string'
          ? exp.progress_label
          : (hasStartedOnce ? `${expProgress !== null ? expProgress : 0}%` : 'NA');
    
      const infiniteBadge = hasInfiniteClient ? 
          `<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="Infinite">∞</span>` : '';
    
      const clientCountBadge = clientCount > 0 ?
          `<span style="background: #e0e0e0; color: #666; font-size: 0.6em; padding: 0 4px; border-radius: 6px; line-height: 1.4;" title="Clients">${clientCount}</span>` : '';

      const progressBadge = (expStatus === 'stopped' || expStatus === 'scheduled') ?
          `<span style="background: linear-gradient(90deg, #039be5 0%, #00b4d8 100%); color: white; font-size: 0.65em; padding: 1px 6px; border-radius: 8px; font-weight: 600; line-height: 1.4; white-space: nowrap;" title="Current execution progress">
              Execution: ${progressLabel}
          </span>` : '';
    
      const runButton = exp.running === 0 ?
          `<a class="link-tooltip" href="#" onclick="startExperimentServer('${exp.idexp}'); return false;" title="Run">
              <i class="mdi mdi-play-box-outline" style="font-size: 16px;"></i>
          </a>` :
          (exp.can_manage ? `<a class="link-tooltip" href="#" onclick="stopExperimentServer('${exp.idexp}'); return false;" title="Stop">
              <i class="mdi mdi-stop active" style="font-size: 16px;"></i>
          </a>` : '');
    
      const deleteExpButton = exp.status === 0 && exp.can_manage ?
          `<a class="link-tooltip" href="javascript:void(0);" 
             onclick="if(confirm('Are you sure you want to delete this experiment? This action cannot be undone.')) { window.location.href='/admin/delete_simulation/${exp.idexp}'; }" 
             title="Delete">
              <i class="mdi mdi-delete" style="font-size: 16px;"></i>
          </a>` : '';
    
      const ownerBadge = exp.owner ? 
          `<span style="background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="Owner">${exp.owner}</span>` : '';

      const platformBadge = `<span style="background: linear-gradient(90deg, #0f766e 0%, #14b8a6 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="Platform">${exp.platform_type === 'forum' ? 'Forum' : exp.platform_type === 'photo_sharing' ? 'Photo Sharing' : 'Microblogging'}</span>`;
    
      const hpcBadge = exp.simulator_type === 'HPC' ?
          `<span style="background: linear-gradient(90deg, #f59e0b 0%, #f97316 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="HPC">HPC</span>` : '';
    
      const remoteBadge = exp.is_remote === 1 ?
          `<span style="background: linear-gradient(90deg, #2196F3 0%, #03A9F4 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="Remote">Remote</span>` : '';
    
      return `
      <div class="box-content" style="background: #fafafa; border: 1px solid #e6e6e6; border-left: 2px solid ${sectionColor}; border-radius: 4px; padding: 4px 8px; margin-bottom: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);">
          <div class="box-lines">
              <div class="box-line" style="padding: 0; display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                  <span class="left" style="display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; overflow: hidden;">
                      <strong style="color: #0d95e8; font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${exp.exp_name}">${exp.exp_name}</strong>
                      ${ownerBadge}
                      ${platformBadge}
                      ${hpcBadge}
                      ${remoteBadge}
                      ${clientCountBadge}
                      ${infiniteBadge}
                  </span>
                  <span class="right" style="display: flex; gap: 2px; align-items: center; flex-shrink: 0;">
                      ${progressBadge}
                      ${runButton}
                      <a class="link-tooltip" href="#" onclick="selectExperiment('${exp.idexp}'); return false;" title="Load">
                          <i class="mdi mdi-select-all ${exp.status === 1 ? 'active' : ''}" style="font-size: 16px;"></i>
                      </a>
                      <a href="/admin/experiment_details/${exp.idexp}" class="link-tooltip" title="Details">
                          <i class="mdi mdi-open-in-new" style="font-size: 14px; color: #039be5;"></i>
                      </a>
                      ${deleteExpButton}
                  </span>
              </div>
          </div>
      </div>`;
  }

  // Render a single experiment box from JSON data (full version for running experiments)
  function renderExperimentBoxFromData(exp, sectionColor, jupyterByExp, notebook, isPyinstaller) {
      const hasInfiniteClient = exp.clients.some(client => client.days === -1);
      const clientsHtml = exp.clients.map(client => {
          let runButtonHtml = '';
          if (client.status === 0 && exp.running === 1) {
              if (client.elapsed === 0) {
                  runButtonHtml = `<a class="link-tooltip" href="/admin/run_client/${client.id}/${exp.idexp}" title="Run Client">
                      <i class="mdi mdi-play-box-outline" style="font-size: 20px;"></i>
                  </a>`;
              } else if (client.expected === -1 || (client.elapsed > 0 && client.elapsed < client.expected)) {
                  runButtonHtml = `<a class="link-tooltip" href="/admin/resume_client/${client.id}/${exp.idexp}" title="Resume Client">
                      <i class="mdi mdi-play-box-outline" style="font-size: 20px;"></i>
                  </a>`;
              }
          }
        
          const pauseButtonHtml = client.status === 1 ? 
              `<a class="link-tooltip" href="/admin/pause_client/${client.id}/${exp.idexp}" title="Pause Client">
                  <i class="mdi mdi-pause active" style="font-size: 20px;"></i>
              </a>` : '';
        
          const deleteButtonHtml = client.status === 0 ?
              `<a class="link-tooltip" href="javascript:void(0);" 
                 onclick="if(confirm('Are you sure you want to delete this client? This action cannot be undone.')) { window.location.href='/admin/delete_client/${client.id}'; }" 
                 title="Delete Client">
                  <i class="mdi mdi-delete" style="font-size: 20px;"></i>
              </a>` : '';
        
          const detailsLink = client.elapsed > 0 ?
              `<a href="/admin/client_details/${client.id}" class="link-tooltip" title="View Client Details">
                  <i class="mdi mdi-open-in-new" style="font-size: 16px; color: #039be5;"></i>
              </a>` : '';
        
          return `
          <div class="box-line" style="padding-left: 20px; padding-top: 8px; padding-bottom: 8px;">
              <span class="left" style="font-size: 0.9em; display: flex; align-items: center; gap: 5px;">Client:
                  <i class="mdi mdi-account-cog" style="font-size: 16px; color: #7f8c8d;"></i>
                  <em style="color: #0d95e8">${client.name}</em>
                  ${detailsLink}
              </span>
              <span class="right" style="width: 55%; display: flex; align-items: center; gap: 10px;">
                  <div class="sleek-progress-container" style="flex: 1; position: relative; background: linear-gradient(to right, #f5f5f5 0%, #e8e8e8 100%); border-radius: 20px; height: 24px; overflow: hidden; box-shadow: inset 0 2px 4px rgba(0,0,0,0.08);">
                      <div id="progress-bar-${client.id}" class="sleek-progress-bar" 
                           style="position: absolute; left: 0; top: 0; height: 100%; width: ${client.progress}%; background: linear-gradient(90deg, #039be5 0%, #4facfe 100%); border-radius: 20px; transition: width 0.4s ease-in-out; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(3,155,229,0.3);">
                          <span style="font-size: 0.75em; font-weight: 600; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.2);">${client.progress}%</span>
                      </div>
                  </div>
                  <div style="display: flex; gap: 3px;">
                      ${runButtonHtml}
                      ${pauseButtonHtml}
                      ${deleteButtonHtml}
                  </div>
              </span>
          </div>`;
      }).join('');
    
      const infiniteBadge = hasInfiniteClient ? 
          `<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="This experiment has at least one client set to run until manually stopped">∞ Infinite</span>` : '';
    
      const runButton = exp.running === 0 ?
          `<a class="link-tooltip" href="#" onclick="startExperimentServer('${exp.idexp}'); return false;" title="Run Experiment">
              <i class="mdi mdi-play-box-outline" style="font-size: 24px;"></i>
          </a>` :
          (exp.can_manage ? `<a class="link-tooltip" href="#" onclick="stopExperimentServer('${exp.idexp}'); return false;" title="Stop Experiment">
              <i class="mdi mdi-stop active" style="font-size: 24px;"></i>
          </a>` : '');
    
      const joinButton = exp.status === 1 ?
          `<a class="link-tooltip" href="#" onclick="joinExperiment('${exp.idexp}'); return false;" title="Join This Experiment">
              <i class="mdi mdi-login" style="font-size: 24px;"></i>
          </a>` : '';
    
      const deleteExpButton = exp.status === 0 && exp.can_manage ?
          `<a class="link-tooltip" href="javascript:void(0);" 
             onclick="if(confirm('Are you sure you want to delete this experiment? This action cannot be undone.')) { window.location.href='/admin/delete_simulation/${exp.idexp}'; }" 
             title="Delete Experiment">
              <i class="mdi mdi-delete" style="font-size: 24px;"></i>
          </a>` : '';
    
      const clientsSeparator = exp.clients.length > 0 ? 
          '<hr style="border-top: 2px solid #e6e6e6; margin-top: 0px; padding-top: 0px; margin-bottom: 0px;">' : '';
    
      const ownerBadgeFull = exp.owner ?
          `<span style="background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="Experiment owner">${exp.owner}</span>` : '';

      const platformBadgeFull = `<span style="background: linear-gradient(90deg, #0f766e 0%, #14b8a6 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="Platform">${exp.platform_type === 'forum' ? 'Forum' : exp.platform_type === 'photo_sharing' ? 'Photo Sharing' : 'Microblogging'}</span>`;
    
      const hpcBadgeFull = exp.simulator_type === 'HPC' ?
          `<span style="background: linear-gradient(90deg, #f59e0b 0%, #f97316 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="HPC Simulator">HPC</span>` : '';
    
      const remoteBadgeFull = exp.is_remote === 1 ?
          `<span style="background: linear-gradient(90deg, #2196F3 0%, #03A9F4 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="Remote Experiment">Remote</span>` : '';
    
      return `
      <div class="box-content" style="background: #fafafa; border: 1px solid #e6e6e6; border-left: 4px solid ${sectionColor}; border-radius: 8px; padding-left: 15px; padding-right: 15px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
          <div class="box-lines">
              <div class="box-line" style="padding-bottom: 5px; margin-bottom: 5px;">
                  <span class="left" style="display: flex; align-items: center; gap: 10px;">
                      Experiment: <strong style="color: #0d95e8">${exp.exp_name}</strong>
                      ${ownerBadgeFull}
                      ${platformBadgeFull}
                      ${hpcBadgeFull}
                      ${remoteBadgeFull}
                      ${infiniteBadge}
                      <a href="/admin/experiment_details/${exp.idexp}" class="link-tooltip" title="View Experiment Details">
                          <i class="mdi mdi-open-in-new" style="font-size: 16px; color: #039be5;"></i>
                      </a>
                  </span>
                  <span class="right" style="display: flex; gap: 8px; align-items: center;">
                      <div style="display: flex; gap: 3px; padding-right: 8px; border-right: 1px solid #ddd;">
                          ${runButton}
                          <a class="link-tooltip" href="#" onclick="selectExperiment('${exp.idexp}'); return false;" title="Load Experiment">
                              <i class="mdi mdi-select-all ${exp.status === 1 ? 'active' : ''}" style="font-size: 24px;"></i>
                          </a>
                          ${joinButton}
                          ${deleteExpButton}
                      </div>
                  </span>
              </div>
              ${clientsSeparator}
              ${clientsHtml}
          </div>
      </div>`;
  }

  // Pagination state - will be initialized when experiments exist
  let paginationState = {
      running: { page: 1, totalPages: YS_DATA_DASHBOARD.totalRunning > 0 ? Math.floor((YS_DATA_DASHBOARD.totalRunning - 1) / 5) + 1 : 1 },
      completed: { page: 1, totalPages: YS_DATA_DASHBOARD.totalCompleted > 0 ? Math.floor((YS_DATA_DASHBOARD.totalCompleted - 1) / 5) + 1 : 1 },
      stopped: { page: 1, totalPages: YS_DATA_DASHBOARD.totalStopped > 0 ? Math.floor((YS_DATA_DASHBOARD.totalStopped - 1) / 5) + 1 : 1 }
  };

  // Async pagination for running experiments
  async function paginateRunning(direction) {
      const newPage = paginationState.running.page + direction;
      if (newPage < 1 || newPage > paginationState.running.totalPages) return;
    
      try {
          const response = await fetch(`/admin/dashboard/experiments/running?page=${newPage}&per_page=5`);
          const data = await response.json();
        
          if (data.experiments) {
              paginationState.running.page = newPage;
              paginationState.running.totalPages = data.total_pages;
            
              const container = document.getElementById('running-experiments-container');
              if (container) {
                  const html = data.experiments.map(exp => renderExperimentBoxFromData(exp, '#28a745', {}, false, false)).join('');
                  container.innerHTML = html || '<p style="color: #666; text-align: center;">No experiments</p>';
              }
            
              // Update pagination buttons
              const prevBtn = document.getElementById('running-prev');
              const nextBtn = document.getElementById('running-next');
              const pageInfo = document.getElementById('running-page-info');
              if (prevBtn) prevBtn.disabled = newPage <= 1;
              if (nextBtn) nextBtn.disabled = newPage >= data.total_pages;
              if (pageInfo) pageInfo.textContent = `Page ${newPage} of ${data.total_pages}`;
          }
      } catch (error) {
          console.error('Error paginating running experiments:', error);
      }
  }

  // Async pagination for completed experiments
  async function paginateCompleted(direction) {
      const newPage = paginationState.completed.page + direction;
      if (newPage < 1 || newPage > paginationState.completed.totalPages) return;
    
      try {
          const response = await fetch(`/admin/dashboard/experiments/completed?page=${newPage}&per_page=5`);
          const data = await response.json();
        
          if (data.experiments) {
              paginationState.completed.page = newPage;
              paginationState.completed.totalPages = data.total_pages;
            
              const container = document.getElementById('completed-experiments-container');
              if (container) {
                  const html = data.experiments.map(exp => renderCompactExperimentBoxFromData(exp, '#17a2b8')).join('');
                  container.innerHTML = html || '<p style="color: #666; text-align: center;">No experiments</p>';
              }
            
              // Update pagination buttons
              const prevBtn = document.getElementById('completed-prev');
              const nextBtn = document.getElementById('completed-next');
              const pageInfo = document.getElementById('completed-page-info');
              if (prevBtn) prevBtn.disabled = newPage <= 1;
              if (nextBtn) nextBtn.disabled = newPage >= data.total_pages;
              if (pageInfo) pageInfo.textContent = `${newPage}/${data.total_pages}`;
          }
      } catch (error) {
          console.error('Error paginating completed experiments:', error);
      }
  }

  // Async pagination for stopped experiments
  async function paginateStopped(direction) {
      const newPage = paginationState.stopped.page + direction;
      if (newPage < 1 || newPage > paginationState.stopped.totalPages) return;
    
      try {
          const response = await fetch(`/admin/dashboard/experiments/stopped?page=${newPage}&per_page=5`);
          const data = await response.json();
        
          if (data.experiments) {
              paginationState.stopped.page = newPage;
              paginationState.stopped.totalPages = data.total_pages;
            
              const container = document.getElementById('stopped-experiments-container');
              if (container) {
                  const html = data.experiments.map(exp => renderCompactExperimentBoxFromData(exp, '#6c757d')).join('');
                  container.innerHTML = html || '<p style="color: #666; text-align: center;">No experiments</p>';
              }
            
              // Update pagination buttons
              const prevBtn = document.getElementById('stopped-prev');
              const nextBtn = document.getElementById('stopped-next');
              const pageInfo = document.getElementById('stopped-page-info');
              if (prevBtn) prevBtn.disabled = newPage <= 1;
              if (nextBtn) nextBtn.disabled = newPage >= data.total_pages;
              if (pageInfo) pageInfo.textContent = `${newPage}/${data.total_pages}`;
          }
      } catch (error) {
          console.error('Error paginating stopped experiments:', error);
      }
  }


async function markRead(id) {
    try {
        const response = await fetch(`/admin/notifications/${id}/read`, {
            method: 'POST'
        });
        const data = await response.json();
        if (data.success) {
            window.location.reload();
        }
    } catch (error) {
        console.error('Failed to mark notification as read:', error);
    }
}

async function deleteNotification(id) {
    if (!confirm('Delete this notification and remove attached file if present?')) {
        return;
    }

    try {
        const response = await fetch(`/admin/notifications/${id}/delete`, {
            method: 'POST'
        });
        const data = await response.json();
        if (data.success) {
            window.location.reload();
        }
    } catch (error) {
        console.error('Failed to delete notification:', error);
    }
}

  // Auto-reload if Jupyter is not responding
  setTimeout(function() {
      var frame = document.getElementById('jupyter-frame');
      if (!frame) return;
      frame.addEventListener('error', function() {
          var config = window.YS_DATA_JUPYTER || {};
          alert('Jupyter Lab appears to be offline. Redirecting to home...');
          window.location.href = config.homeUrl || '/';
      });
  }, 5000);

  // Expose globally for HTML onclick attributes
  window.markRead = markRead;
  window.deleteNotification = deleteNotification;
  window.toggleGroup = toggleGroup;
  window.dismissTelemetryNotice = dismissTelemetryNotice;
  window.startJupyterSession = startJupyterSession;
  window.stopJupyterSession = stopJupyterSession;
  window.startExperimentServer = startExperimentServer;
  window.stopExperimentServer = stopExperimentServer;
  window.selectExperiment = selectExperiment;
  window.joinExperiment = joinExperiment;



})();
