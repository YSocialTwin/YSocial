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
      const element = progressBar && progressBar.jquery ? progressBar[0] : progressBar;
      if (!element) {
          return;
      }

      if (data.infinite) {
          element.style.width = '100%';
          element.style.background = 'linear-gradient(90deg, #22c55e 0%, #4ade80 100%)';
          element.style.boxShadow = '0 2px 6px rgba(34,197,94,0.3)';

          const days = data.elapsed_days || 0;
          const hours = data.elapsed_hours || 0;
          const timeText = days > 0 ? (days + 'd ' + hours + 'h') : (hours + 'h elapsed');
          const label = element.querySelector('span');
          if (label) {
              label.textContent = '∞ ' + timeText;
          }
          return;
      }

      const percentage = Math.min(100, Math.max(0, data.progress || 0));
      element.style.width = percentage + '%';
      const label = element.querySelector('span');
      if (label) {
          label.textContent = percentage + '%';
      }

      if (percentage >= 75) {
          element.style.background = 'linear-gradient(90deg, #039be5 0%, #00d1b2 100%)';
          element.style.boxShadow = '0 2px 6px rgba(0,209,178,0.3)';
      } else if (percentage >= 50) {
          element.style.background = 'linear-gradient(90deg, #039be5 0%, #5596e6 100%)';
          element.style.boxShadow = '0 2px 6px rgba(85,150,230,0.3)';
      } else {
          element.style.background = 'linear-gradient(90deg, #039be5 0%, #4facfe 100%)';
          element.style.boxShadow = '0 2px 6px rgba(3,155,229,0.3)';
      }
  }

  const experimentProgressRequests = {};
  const PROGRESS_REFRESH_INTERVAL = 5000;

  function getRunningExperimentIds() {
      const container = document.getElementById('running-experiments-container');
      if (!container) {
          return [];
      }

      const expIds = new Set();
      container.querySelectorAll('[data-exp-id]').forEach((element) => {
          const expId = element.dataset.expId;
          if (expId) {
              expIds.add(expId);
          }
      });
      return Array.from(expIds);
  }

  function refreshExperimentProgress(expId) {
      if (!expId || experimentProgressRequests[expId]) {
          return;
      }

      experimentProgressRequests[expId] = true;

      fetch(`/admin/experiment_clients/${expId}`)
          .then(response => response.json())
          .then(data => {
              if (data.error || !data.clients || data.clients.length === 0) {
                  return;
              }

              data.clients.forEach((client) => {
                  const progressBar = document.getElementById(`progress-bar-${client.id}`);
                  if (progressBar) {
                      applyProgressBarState(progressBar, client);
                  }
              });
          })
          .catch((error) => {
              console.error(`Error refreshing progress for experiment ${expId}:`, error);
          })
          .finally(() => {
              experimentProgressRequests[expId] = false;
          });
  }

  function refreshAllClientProgress() {
      getRunningExperimentIds().forEach((expId) => {
          refreshExperimentProgress(expId);
      });
  }

  $(document).ready(function () {
      refreshAllClientProgress();
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
                  refreshExperimentSection(
                      'running',
                      '#28a745',
                      paginationState.running.page
                  ),
                  refreshExperimentSection(
                      'completed',
                      '#17a2b8',
                      paginationState.completed.page
                  ),
                  refreshExperimentSection(
                      'stopped',
                      '#6c757d',
                      paginationState.stopped.page
                  )
              ]);
          }
      } catch (error) {
          console.error('Error refreshing dashboard:', error);
      }
  }

  async function refreshExperimentSection(status, sectionColor, page) {
      try {
          const currentPage = Math.max(
              1,
              page || paginationState[status].page || 1
          );
          const response = await fetch(
              `/admin/dashboard/experiments/${status}?page=${currentPage}&per_page=5`
          );
          const data = await response.json();
        
          const containerId = `${status === 'running' ? 'running' : status}-experiments-container`;
          const container = document.getElementById(containerId);
        
          if (container && data.experiments) {
              const totalPages = data.total_pages || 1;
              paginationState[status].page = Math.min(currentPage, totalPages);
              paginationState[status].totalPages = totalPages;

              // Use compact rendering for completed/stopped, full for running
              const renderFunc = status === 'running' 
                  ? (exp) => renderExperimentBoxFromData(exp, sectionColor, {}, false, false)
                  : (exp) => renderCompactExperimentBoxFromData(exp, sectionColor);
              const html = data.experiments.map(renderFunc).join('');
              container.innerHTML = html || '<p style="color: #666; text-align: center;">' + YI18n.t('No experiments in this category') + '</p>';

              const prevBtn = document.getElementById(`${status}-prev`);
              const nextBtn = document.getElementById(`${status}-next`);
              const pageInfo = document.getElementById(`${status}-page-info`);
              if (prevBtn) prevBtn.disabled = paginationState[status].page <= 1;
              if (nextBtn) nextBtn.disabled = paginationState[status].page >= totalPages;
              if (pageInfo) {
                  pageInfo.textContent = status === 'running'
                      ? YI18n.t('Page {page} of {totalpages}', {page: paginationState[status].page, totalpages: totalPages})
                      : `${paginationState[status].page}/${totalPages}`;
              }
          }
      } catch (error) {
          console.error(`Error refreshing ${status} experiments:`, error);
      }
  }

  // Start periodic async refresh
  setInterval(refreshDashboardAsync, DASHBOARD_REFRESH_INTERVAL);
  setInterval(refreshAllClientProgress, PROGRESS_REFRESH_INTERVAL);

  // Experiment server control functions
  function startExperimentServer(expId) {
      showLoading(YI18n.t('Starting experiment server...'));
      window.location.href = `/admin/start_experiment/${expId}`;
  }

  function stopExperimentServer(expId) {
      showLoading(YI18n.t('Stopping experiment server...'));
      window.location.href = `/admin/stop_experiment/${expId}`;
  }

  function selectExperiment(expId) {
      showLoading(YI18n.t('Loading experiment interface...'));
      window.location.href = `/admin/select_experiment/${expId}`;
  }

  function joinExperiment(expId) {
      showLoading(YI18n.t('Joining experiment...'));
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
          '<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="' + YI18n.t('Infinite') + '">∞</span>' : '';
    
      const clientCountBadge = clientCount > 0 ?
          '<span style="background: #e0e0e0; color: #666; font-size: 0.6em; padding: 0 4px; border-radius: 6px; line-height: 1.4;" title="' + YI18n.t('Clients') + '">' + clientCount + '</span>' : '';

      const progressBadge = (expStatus === 'stopped' || expStatus === 'scheduled') ?
          '<span style="background: linear-gradient(90deg, #039be5 0%, #00b4d8 100%); color: white; font-size: 0.65em; padding: 1px 6px; border-radius: 8px; font-weight: 600; line-height: 1.4; white-space: nowrap;" title="' + YI18n.t('Current execution progress') + '">\n              ' + YI18n.t('Execution: {progresslabel}', {progresslabel: progressLabel}) + '\n          </span>' : '';
    
      const runButton = exp.running === 0 ?
          '<a class="link-tooltip" href="#" onclick="startExperimentServer(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Run') + '">\n              <i class="mdi mdi-play-box-outline" style="font-size: 16px;"></i>\n          </a>' :
          (exp.can_manage ? '<a class="link-tooltip" href="#" onclick="stopExperimentServer(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Stop') + '">\n              <i class="mdi mdi-stop active" style="font-size: 16px;"></i>\n          </a>' : '');
    
      const deleteExpButton = exp.status === 0 && exp.can_manage ?
          '<a class="link-tooltip" href="javascript:void(0);" \n             onclick="if(confirm(YI18n.t(\'Are you sure you want to delete this experiment? This action cannot be undone.\'))) { window.location.href=\'/admin/delete_simulation/' + exp.idexp + '\'; }" \n             title="' + YI18n.t('Delete') + '">\n              <i class="mdi mdi-delete" style="font-size: 16px;"></i>\n          </a>' : '';
    
      const ownerBadge = exp.owner ? 
          '<span style="background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="' + YI18n.t('Owner') + '">' + exp.owner + '</span>' : '';

      const platformBadge = '<span style="background: linear-gradient(90deg, #0f766e 0%, #14b8a6 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="' + YI18n.t('Platform') + '">' + (exp.platform_type === 'forum' ? 'Forum' : exp.platform_type === 'photo_sharing' ? 'Photo Sharing' : 'Microblogging') + '</span>';
    
      const hpcBadge = exp.simulator_type === 'HPC' ?
          '<span style="background: linear-gradient(90deg, #f59e0b 0%, #f97316 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="' + YI18n.t('HPC') + '">' + YI18n.t('HPC') + '</span>' : '';
    
      const remoteBadge = exp.is_remote === 1 ?
          '<span style="background: linear-gradient(90deg, #2196F3 0%, #03A9F4 100%); color: white; font-size: 0.6em; padding: 0 4px; border-radius: 6px; font-weight: 600; line-height: 1.4;" title="' + YI18n.t('Remote') + '">' + YI18n.t('Remote') + '</span>' : '';
    
      return '\n      <div class="box-content" style="background: #fafafa; border: 1px solid #e6e6e6; border-left: 2px solid ' + sectionColor + '; border-radius: 4px; padding: 4px 8px; margin-bottom: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);">\n          <div class="box-lines">\n              <div class="box-line" style="padding: 0; display: flex; align-items: center; justify-content: space-between; gap: 4px;">\n                  <span class="left" style="display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; overflow: hidden;">\n                      <strong style="color: #0d95e8; font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="' + exp.exp_name + '">' + exp.exp_name + '</strong>\n                      ' + ownerBadge + '\n                      ' + platformBadge + '\n                      ' + hpcBadge + '\n                      ' + remoteBadge + '\n                      ' + clientCountBadge + '\n                      ' + infiniteBadge + '\n                  </span>\n                  <span class="right" style="display: flex; gap: 2px; align-items: center; flex-shrink: 0;">\n                      ' + progressBadge + '\n                      ' + runButton + '\n                      <a class="link-tooltip" href="#" onclick="selectExperiment(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Load') + '">\n                          <i class="mdi mdi-select-all ' + (exp.status === 1 ? 'active' : '') + '" style="font-size: 16px;"></i>\n                      </a>\n                      <a href="/admin/experiment_details/' + exp.idexp + '" class="link-tooltip" title="' + YI18n.t('Details') + '">\n                          <i class="mdi mdi-open-in-new" style="font-size: 14px; color: #039be5;"></i>\n                      </a>\n                      ' + deleteExpButton + '\n                  </span>\n              </div>\n          </div>\n      </div>';
  }

  // Render a single experiment box from JSON data (full version for running experiments)
  function renderExperimentBoxFromData(exp, sectionColor, jupyterByExp, notebook, isPyinstaller) {
      const hasInfiniteClient = exp.clients.some(client => client.days === -1);
      const clientsHtml = exp.clients.map(client => {
          let runButtonHtml = '';
          if (client.status === 0 && exp.running === 1) {
              if (client.elapsed === 0) {
                  runButtonHtml = '<a class="link-tooltip" href="/admin/run_client/' + client.id + '/' + exp.idexp + '" title="' + YI18n.t('Run Client') + '">\n                      <i class="mdi mdi-play-box-outline" style="font-size: 20px;"></i>\n                  </a>';
              } else if (client.expected === -1 || (client.elapsed > 0 && client.elapsed < client.expected)) {
                  runButtonHtml = '<a class="link-tooltip" href="/admin/resume_client/' + client.id + '/' + exp.idexp + '" title="' + YI18n.t('Resume Client') + '">\n                      <i class="mdi mdi-play-box-outline" style="font-size: 20px;"></i>\n                  </a>';
              }
          }
        
          const pauseButtonHtml = client.status === 1 ? 
              '<a class="link-tooltip" href="/admin/pause_client/' + client.id + '/' + exp.idexp + '" title="' + YI18n.t('Pause Client') + '">\n                  <i class="mdi mdi-pause active" style="font-size: 20px;"></i>\n              </a>' : '';
        
          const deleteButtonHtml = client.status === 0 ?
              '<a class="link-tooltip" href="javascript:void(0);" \n                 onclick="if(confirm(YI18n.t(\'Are you sure you want to delete this client? This action cannot be undone.\'))) { window.location.href=\'/admin/delete_client/' + client.id + '\'; }" \n                 title="' + YI18n.t('Delete Client') + '">\n                  <i class="mdi mdi-delete" style="font-size: 20px;"></i>\n              </a>' : '';
        
          const detailsLink = client.elapsed > 0 ?
              '<a href="/admin/client_details/' + client.id + '" class="link-tooltip" title="' + YI18n.t('View Client Details') + '">\n                  <i class="mdi mdi-open-in-new" style="font-size: 16px; color: #039be5;"></i>\n              </a>' : '';
        
          return '\n          <div class="box-line" style="padding-left: 20px; padding-top: 8px; padding-bottom: 8px;">\n              <span class="left" style="font-size: 0.9em; display: flex; align-items: center; gap: 5px;">' + YI18n.t('Client:') + '\n                  <i class="mdi mdi-account-cog" style="font-size: 16px; color: #7f8c8d;"></i>\n                  <em style="color: #0d95e8">' + client.name + '</em>\n                  ' + detailsLink + '\n              </span>\n              <span class="right" style="width: 55%; display: flex; align-items: center; gap: 10px;">\n                  <div class="sleek-progress-container" style="flex: 1; position: relative; background: linear-gradient(to right, #f5f5f5 0%, #e8e8e8 100%); border-radius: 20px; height: 24px; overflow: hidden; box-shadow: inset 0 2px 4px rgba(0,0,0,0.08);">\n                      <div id="progress-bar-' + client.id + '" class="sleek-progress-bar" data-exp-id="' + exp.idexp + '"\n                           style="position: absolute; left: 0; top: 0; height: 100%; width: ' + client.progress + '%; background: linear-gradient(90deg, #039be5 0%, #4facfe 100%); border-radius: 20px; transition: width 0.4s ease-in-out; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(3,155,229,0.3);">\n                          <span style="font-size: 0.75em; font-weight: 600; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.2);">' + client.progress + '%</span>\n                      </div>\n                  </div>\n                  <div style="display: flex; gap: 3px;">\n                      ' + runButtonHtml + '\n                      ' + pauseButtonHtml + '\n                      ' + deleteButtonHtml + '\n                  </div>\n              </span>\n          </div>';
      }).join('');
    
      const infiniteBadge = hasInfiniteClient ? 
          '<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="' + YI18n.t('This experiment has at least one client set to run until manually stopped') + '">' + YI18n.t('∞ Infinite') + '</span>' : '';
    
      const runButton = exp.running === 0 ?
          '<a class="link-tooltip" href="#" onclick="startExperimentServer(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Run Experiment') + '">\n              <i class="mdi mdi-play-box-outline" style="font-size: 24px;"></i>\n          </a>' :
          (exp.can_manage ? '<a class="link-tooltip" href="#" onclick="stopExperimentServer(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Stop Experiment') + '">\n              <i class="mdi mdi-stop active" style="font-size: 24px;"></i>\n          </a>' : '');
    
      const joinButton = exp.status === 1 ?
          '<a class="link-tooltip" href="#" onclick="joinExperiment(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Join This Experiment') + '">\n              <i class="mdi mdi-login" style="font-size: 24px;"></i>\n          </a>' : '';
    
      const deleteExpButton = exp.status === 0 && exp.can_manage ?
          '<a class="link-tooltip" href="javascript:void(0);" \n             onclick="if(confirm(YI18n.t(\'Are you sure you want to delete this experiment? This action cannot be undone.\'))) { window.location.href=\'/admin/delete_simulation/' + exp.idexp + '\'; }" \n             title="' + YI18n.t('Delete Experiment') + '">\n              <i class="mdi mdi-delete" style="font-size: 24px;"></i>\n          </a>' : '';
    
      const clientsSeparator = exp.clients.length > 0 ? 
          '<hr style="border-top: 2px solid #e6e6e6; margin-top: 0px; padding-top: 0px; margin-bottom: 0px;">' : '';
    
      const ownerBadgeFull = exp.owner ?
          '<span style="background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="' + YI18n.t('Experiment owner') + '">' + exp.owner + '</span>' : '';

      const platformBadgeFull = '<span style="background: linear-gradient(90deg, #0f766e 0%, #14b8a6 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="' + YI18n.t('Platform') + '">' + (exp.platform_type === 'forum' ? 'Forum' : exp.platform_type === 'photo_sharing' ? 'Photo Sharing' : 'Microblogging') + '</span>';
    
      const hpcBadgeFull = exp.simulator_type === 'HPC' ?
          '<span style="background: linear-gradient(90deg, #f59e0b 0%, #f97316 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="' + YI18n.t('HPC Simulator') + '">' + YI18n.t('HPC') + '</span>' : '';
    
      const remoteBadgeFull = exp.is_remote === 1 ?
          '<span style="background: linear-gradient(90deg, #2196F3 0%, #03A9F4 100%); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: 600;" title="' + YI18n.t('Remote Experiment') + '">' + YI18n.t('Remote') + '</span>' : '';
    
      return '\n      <div class="box-content" style="background: #fafafa; border: 1px solid #e6e6e6; border-left: 4px solid ' + sectionColor + '; border-radius: 8px; padding-left: 15px; padding-right: 15px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">\n          <div class="box-lines">\n              <div class="box-line" style="padding-bottom: 5px; margin-bottom: 5px;">\n                  <span class="left" style="display: flex; align-items: center; gap: 10px;">\n                      ' + YI18n.t('Experiment:') + ' <strong style="color: #0d95e8">' + exp.exp_name + '</strong>\n                      ' + ownerBadgeFull + '\n                      ' + platformBadgeFull + '\n                      ' + hpcBadgeFull + '\n                      ' + remoteBadgeFull + '\n                      ' + infiniteBadge + '\n                      <a href="/admin/experiment_details/' + exp.idexp + '" class="link-tooltip" title="' + YI18n.t('View Experiment Details') + '">\n                          <i class="mdi mdi-open-in-new" style="font-size: 16px; color: #039be5;"></i>\n                      </a>\n                  </span>\n                  <span class="right" style="display: flex; gap: 8px; align-items: center;">\n                      <div style="display: flex; gap: 3px; padding-right: 8px; border-right: 1px solid #ddd;">\n                          ' + runButton + '\n                          <a class="link-tooltip" href="#" onclick="selectExperiment(\'' + exp.idexp + '\'); return false;" title="' + YI18n.t('Load Experiment') + '">\n                              <i class="mdi mdi-select-all ' + (exp.status === 1 ? 'active' : '') + '" style="font-size: 24px;"></i>\n                          </a>\n                          ' + joinButton + '\n                          ' + deleteExpButton + '\n                      </div>\n                  </span>\n              </div>\n              ' + clientsSeparator + '\n              ' + clientsHtml + '\n          </div>\n      </div>';
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
                  container.innerHTML = html || '<p style="color: #666; text-align: center;">' + YI18n.t('No experiments') + '</p>';
              }
            
              // Update pagination buttons
              const prevBtn = document.getElementById('running-prev');
              const nextBtn = document.getElementById('running-next');
              const pageInfo = document.getElementById('running-page-info');
              if (prevBtn) prevBtn.disabled = newPage <= 1;
              if (nextBtn) nextBtn.disabled = newPage >= data.total_pages;
              if (pageInfo) pageInfo.textContent = YI18n.t('Page {newpage} of {total_pages}', {newpage: newPage, total_pages: data.total_pages});
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
                  container.innerHTML = html || '<p style="color: #666; text-align: center;">' + YI18n.t('No experiments') + '</p>';
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
                  container.innerHTML = html || '<p style="color: #666; text-align: center;">' + YI18n.t('No experiments') + '</p>';
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
    if (!confirm(YI18n.t('Delete this notification and remove attached file if present?'))) {
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
          alert(YI18n.t('Jupyter Lab appears to be offline. Redirecting to home...'));
          window.location.href = config.homeUrl || '/';
      });
  }, 5000);

  // Training section: switch a module on/off (archive/unarchive in the plugin)
  function initTrainingToggles() {
      var section = document.getElementById('section-training');
      if (!section) return;
      var token = section.getAttribute('data-csrf') || '';
      section.addEventListener('click', function(ev) {
          var btn = ev.target.closest('.dash-module-toggle');
          if (!btn || btn.disabled) return;
          btn.disabled = true;
          fetch('/admin/training/api/modules/' + encodeURIComponent(btn.dataset.moduleUid) + '/' + btn.dataset.moduleAction, {
              method: 'POST',
              headers: {'Content-Type': 'application/json', 'X-CSRF-Token': token},
              body: '{}'
          }).then(function(resp) {
              if (!resp.ok) throw new Error(resp.status);
              window.location.reload();
          }).catch(function() {
              btn.disabled = false;
              alert(YI18n.t('Could not update the module. Please try again.'));
          });
      });
  }
  initTrainingToggles();

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
  window.paginateRunning = paginateRunning;
  window.paginateCompleted = paginateCompleted;
  window.paginateStopped = paginateStopped;



})();
