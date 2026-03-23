/**
 * AdminSettings - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminSettings = (function() {
  // Status configuration
  const EXP_STATUS = {
      ACTIVE: 'active',
      COMPLETED: 'completed',
      STOPPED_SCHEDULED: 'stopped_scheduled'
  };

  // Store grid instances for refresh
  // const gridInstances = {};  // No longer using Grid.js
  const DATA_REFRESH_INTERVAL = 30000; // 30 seconds

  const updateUrl = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes = (data, row, col) => {
      if (row) {
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': col.id
          };
      } else {
          return {};
      }
  };

  // Functions to start/stop experiment servers
  function startExperimentServer(expId) {
      if (!confirm('Start the experiment server?')) return;
    
      // Show loading
      const btn = event.target.closest('a');
      if (btn) btn.innerHTML = '<i class="mdi mdi-loading mdi-spin" style="font-size: 18px;"></i>';
    
      // Navigate to start endpoint
      window.location.href = `/admin/start_experiment/${expId}`;
  }

  function stopExperimentServer(expId) {
      if (!confirm('Stop the experiment server?')) return;
    
      // Show loading
      const btn = event.target.closest('a');
      if (btn) btn.innerHTML = '<i class="mdi mdi-loading mdi-spin" style="font-size: 18px;"></i>';
    
      // Navigate to stop endpoint
      window.location.href = `/admin/stop_experiment/${expId}`;
  }

  // Function to create compact table columns configuration for Running Experiments
  function getRunningTableColumns() {
      return [
          { id: 'idexp', hidden: true },
          { id: 'has_infinite_client', hidden: true },
          { 
              id: 'exp_name', 
              name: 'Name', 
              attributes: editableCellAttributes, 
              width: '100px',
              formatter: (cell, row) => {
                  const hasInfinite = row.cells[1].data;
                  const infiniteTag = hasInfinite ? 
                      '<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.65em; padding: 1px 4px; border-radius: 8px; font-weight: 600; margin-left: 5px;" title="This experiment has at least one client set to run until manually stopped">∞</span>' : '';
                  return gridjs.html(`<span>${cell}${infiniteTag}</span>`);
              }
          },
          { id: 'owner', name: 'Owner', sort: false, width: '50px' },
          {
              id: 'progress',
              name: 'Progress',
              sort: false,
              width: '100px',
              formatter: (cell, row) => {
                  const progress = cell || 0;
                  const expId = row.cells[0].data;
                  // Gradient colors based on progress
                  let bgColor = 'linear-gradient(90deg, #039be5 0%, #4facfe 100%)';
                  let shadowColor = 'rgba(3,155,229,0.3)';
                  if (progress >= 75) {
                      bgColor = 'linear-gradient(90deg, #039be5 0%, #00d1b2 100%)';
                      shadowColor = 'rgba(0,209,178,0.3)';
                  } else if (progress >= 50) {
                      bgColor = 'linear-gradient(90deg, #039be5 0%, #5596e6 100%)';
                      shadowColor = 'rgba(85,150,230,0.3)';
                  }
                  return gridjs.html(`
                      <div style="position: relative; background: linear-gradient(to right, #f5f5f5 0%, #e8e8e8 100%); border-radius: 12px; height: 18px; overflow: hidden; box-shadow: inset 0 1px 3px rgba(0,0,0,0.08);">
                          <div class="exp-progress-bar" data-exp-id="${expId}" 
                               style="position: absolute; left: 0; top: 0; height: 100%; width: ${progress}%; background: ${bgColor}; border-radius: 12px; transition: width 0.4s ease-in-out; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 4px ${shadowColor};">
                              <span style="font-size: 0.65em; font-weight: 600; color: white; text-shadow: 0 1px 1px rgba(0,0,0,0.2);">${progress}%</span>
                          </div>
                      </div>
                  `);
              }
          },
          {
              id: 'status_combined',
              name: 'Status',
              sort: false,
              width: '40px',
              formatter: (cell, row) => {
                  // Get the web value from hidden cell (shifted by 1 due to has_infinite_client column)
                  const web = row.cells[5].data;      // web is at index 5
                  if (YS_DATA_SETTINGS.enableNotebook) {
                  const jupyter = row.cells[6].data;  // jupyter_status is at index 6
                  }
                
                  const webColor = web === 'Loaded' ? '#28a745' : '#6c757d';
                  if (YS_DATA_SETTINGS.enableNotebook) {
                  const jupyterColor = jupyter === 'Active' ? '#28a745' : '#6c757d';
                  }
                
                  return gridjs.html(`
                      <div class="status-indicators">
                          <span class="status-dot" style="background-color: ${webColor};" title="Web: ${web}"></span>
                          if (YS_DATA_SETTINGS.enableNotebook) {
                          <span class="status-dot" style="background-color: ${jupyterColor};" title="Lab: ${jupyter}"></span>
                          }
                      </div>
                  `);
              }
          },
          { id: 'web', hidden: true },
          if (YS_DATA_SETTINGS.enableNotebook) {
          { id: 'jupyter_status', hidden: true },
          }
          {
              id: 'details',
              name: '',
              sort: false,
              width: '45px',
              formatter: (cell, row) => {
                  const id = row.cells[0].data;
                  return gridjs.html(`
                      <div style="display: flex; flex-direction: column; gap: 3px; align-items: center;">
                          <a href="/admin/experiment_details/${id}" class="box-action-link"
                             style="background-color: #28a745; color: white; padding: 3px 6px; border-radius: 3px; text-decoration: none; font-size: 0.7rem; width: 100%; text-align: center;">
                              <i class="mdi mdi-open-in-new"></i><span class="action-text"> View</span>
                          </a>
                          <a href="/admin/delete_simulation/${id}" class="box-action-link"
                             style="background-color: #dc3545; color: white; padding: 3px 6px; border-radius: 3px; text-decoration: none; font-size: 0.7rem; width: 100%; text-align: center;">
                              <i class="mdi mdi-delete"></i><span class="action-text"> Delete</span>
                          </a>
                      </div>
                  `);
              }
          },
      ];
  }

  // Function to create compact table columns configuration for non-running experiments
  function getTableColumns() {
      return [
          { id: 'idexp', hidden: true },
          { id: 'has_infinite_client', hidden: true },
          { 
              id: 'exp_name', 
              name: 'Name', 
              attributes: editableCellAttributes, 
              width: '100px',
              formatter: (cell, row) => {
                  const hasInfinite = row.cells[1].data;
                  const infiniteTag = hasInfinite ? 
                      '<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.65em; padding: 1px 4px; border-radius: 8px; font-weight: 600; margin-left: 5px;" title="This experiment has at least one client set to run until manually stopped">∞</span>' : '';
                  return gridjs.html(`<span>${cell}${infiniteTag}</span>`);
              }
          },
          { id: 'owner', name: 'Owner', sort: false, width: '50px' },
          {
              id: 'annotations',
              name: 'Tags',
              sort: false,
              width: '70px',
              formatter: (cell) => {
                  if (!cell || cell === '') {
                      return gridjs.html('<div style="text-align: center;">-</div>');
                  }
                  const annotations = cell.split(',').filter(a => a.trim());
                  const tags = annotations.map(annotation => {
                      const colors = {
                          'toxicity': '#dc3545',
                          'sentiment': '#28a745',
                          'emotion': '#17a2b8'
                      };
                      const color = colors[annotation.trim()] || '#6c757d';
                      const shortName = annotation.trim().substring(0, 3);
                      return `<span style="display: inline-block; background-color: ${color}; color: white; padding: 1px 4px; margin: 1px; border-radius: 8px; font-size: 0.65rem;" title="${annotation.trim()}">${shortName}</span>`;
                  }).join('');
                  return gridjs.html(`<div style="display: flex; justify-content: center; flex-wrap: wrap;">${tags}</div>`);
              }
          },
          {
              id: 'status_combined',
              name: 'Status',
              sort: false,
              width: '40px',
              formatter: (cell, row) => {
                  // Get the web value from hidden cell (shifted by 1 due to has_infinite_client column)
                  const web = row.cells[5].data;      // web is at index 5
                  if (YS_DATA_SETTINGS.enableNotebook) {
                  const jupyter = row.cells[6].data;  // jupyter_status is at index 6
                  }
                
                  const webColor = web === 'Loaded' ? '#28a745' : '#6c757d';
                  if (YS_DATA_SETTINGS.enableNotebook) {
                  const jupyterColor = jupyter === 'Active' ? '#28a745' : '#6c757d';
                  }
                
                  return gridjs.html(`
                      <div class="status-indicators">
                          <span class="status-dot" style="background-color: ${webColor};" title="Web: ${web}"></span>
                          if (YS_DATA_SETTINGS.enableNotebook) {
                          <span class="status-dot" style="background-color: ${jupyterColor};" title="Lab: ${jupyter}"></span>
                          }
                      </div>
                  `);
              }
          },
          { id: 'web', hidden: true },
          if (YS_DATA_SETTINGS.enableNotebook) {
          { id: 'jupyter_status', hidden: true },
          }
          {
              id: 'details',
              name: '',
              sort: false,
              width: '45px',
              formatter: (cell, row) => {
                  const id = row.cells[0].data;
                  return gridjs.html(`
                      <div style="display: flex; flex-direction: column; gap: 3px; align-items: center;">
                          <a href="/admin/experiment_details/${id}"
                             style="background-color: #28a745; color: white; padding: 3px 6px; border-radius: 3px; text-decoration: none; font-size: 0.7rem; width: 100%; text-align: center;">
                              View
                          </a>
                          <a href="/admin/delete_simulation/${id}"
                             style="background-color: #dc3545; color: white; padding: 3px 6px; border-radius: 3px; text-decoration: none; font-size: 0.7rem; width: 100%; text-align: center;">
                              Delete
                          </a>
                      </div>
                  `);
              }
          },
      ];
  }

  // Track selected experiments for download
  const selectedExperiments = new Set();

  // Function to update the download button visibility
  function updateDownloadButton() {
      const btn = document.getElementById('download-selected-btn');
      if (btn) {
          if (selectedExperiments.size > 0) {
              btn.style.display = 'inline-block';
              btn.innerHTML = `<i class="mdi mdi-download"></i><span class="exp-btn-label"> Download Selected (${selectedExperiments.size})</span>`;
          } else {
              btn.style.display = 'none';
          }
      }
  }

  // Function to toggle experiment selection
  function toggleExperimentSelection(expId, checkbox) {
      if (checkbox.checked) {
          selectedExperiments.add(expId);
      } else {
          selectedExperiments.delete(expId);
      }
      updateDownloadButton();
      updateSelectAllCheckbox();
  }

  // Function to toggle all experiments selection
  function toggleAllExperiments(masterCheckbox) {
      const checkboxes = document.querySelectorAll('.exp-checkbox');
      checkboxes.forEach(cb => {
          cb.checked = masterCheckbox.checked;
          const expId = parseInt(cb.dataset.expId);
          if (masterCheckbox.checked) {
              selectedExperiments.add(expId);
          } else {
              selectedExperiments.delete(expId);
          }
      });
      updateDownloadButton();
  }

  // Function to update select all checkbox state
  function updateSelectAllCheckbox() {
      const masterCheckbox = document.getElementById('select-all-completed');
      const checkboxes = document.querySelectorAll('.exp-checkbox');
      if (masterCheckbox && checkboxes.length > 0) {
          const allChecked = Array.from(checkboxes).every(cb => cb.checked);
          const someChecked = Array.from(checkboxes).some(cb => cb.checked);
          masterCheckbox.checked = allChecked;
          masterCheckbox.indeterminate = someChecked && !allChecked;
      }
  }

  // Function to download selected experiments
  function downloadSelectedExperiments() {
      if (selectedExperiments.size === 0) {
          alert('Please select at least one experiment to download.');
          return;
      }

      const expIds = Array.from(selectedExperiments);
    
      // Show loading indicator
      const btn = document.getElementById('download-selected-btn');
      const originalText = btn.innerHTML;
      btn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i><span class="exp-btn-label"> Preparing...</span>';
      btn.disabled = true;

      // Submit a form to download (to properly handle file download)
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/admin/download_experiments_bulk';
    
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'exp_ids';
      input.value = JSON.stringify(expIds);
      form.appendChild(input);
    
      document.body.appendChild(form);
      form.submit();
      document.body.removeChild(form);

      // Reset button after a delay
      setTimeout(() => {
          btn.innerHTML = originalText;
          btn.disabled = false;
      }, 3000);
  }

  // Function to download all completed experiments
  function downloadAllExperiments() {
      // Show loading indicator
      const btn = document.getElementById('download-all-btn');
      const originalText = btn.innerHTML;
      btn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i><span class="exp-btn-label"> Preparing...</span>';
      btn.disabled = true;

      // Submit a form to download all (empty array or 'all' signal to backend)
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/admin/download_experiments_bulk';
    
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'exp_ids';
      input.value = JSON.stringify('all');  // Signal to download all completed experiments
      form.appendChild(input);
    
      document.body.appendChild(form);
      form.submit();
      document.body.removeChild(form);

      // Reset button after a delay
      setTimeout(() => {
          btn.innerHTML = originalText;
          btn.disabled = false;
      }, 3000);
  }

  // Function to create compact table columns configuration for Completed Experiments (with checkbox)
  function getCompletedTableColumns() {
      return [
          { id: 'idexp', hidden: true },
          { id: 'has_infinite_client', hidden: true },
          {
              id: 'checkbox',
              name: gridjs.html('<input type="checkbox" id="select-all-completed" onchange="toggleAllExperiments(this)" title="Select all"/>'),
              sort: false,
              width: '30px',
              formatter: (cell, row) => {
                  const id = row.cells[0].data;
                  const isChecked = selectedExperiments.has(id) ? 'checked' : '';
                  return gridjs.html(`
                      <input type="checkbox" class="exp-checkbox" data-exp-id="${id}" 
                             onchange="toggleExperimentSelection(${id}, this)" ${isChecked}
                             style="cursor: pointer;"/>
                  `);
              }
          },
          { 
              id: 'exp_name', 
              name: 'Name', 
              attributes: editableCellAttributes, 
              width: '100px',
              formatter: (cell, row) => {
                  const hasInfinite = row.cells[1].data;
                  const infiniteTag = hasInfinite ? 
                      '<span style="background: linear-gradient(90deg, #22c55e 0%, #4ade80 100%); color: white; font-size: 0.65em; padding: 1px 4px; border-radius: 8px; font-weight: 600; margin-left: 5px;" title="This experiment has at least one client set to run until manually stopped">∞</span>' : '';
                  return gridjs.html(`<span>${cell}${infiniteTag}</span>`);
              }
          },
          { id: 'owner', name: 'Owner', sort: false, width: '50px' },
          {
              id: 'annotations',
              name: 'Tags',
              sort: false,
              width: '70px',
              formatter: (cell) => {
                  if (!cell || cell === '') {
                      return gridjs.html('<div style="text-align: center;">-</div>');
                  }
                  const annotations = cell.split(',').filter(a => a.trim());
                  const tags = annotations.map(annotation => {
                      const colors = {
                          'toxicity': '#dc3545',
                          'sentiment': '#28a745',
                          'emotion': '#17a2b8'
                      };
                      const color = colors[annotation.trim()] || '#6c757d';
                      const shortName = annotation.trim().substring(0, 3);
                      return `<span style="display: inline-block; background-color: ${color}; color: white; padding: 1px 4px; margin: 1px; border-radius: 8px; font-size: 0.65rem;" title="${annotation.trim()}">${shortName}</span>`;
                  }).join('');
                  return gridjs.html(`<div style="display: flex; justify-content: center; flex-wrap: wrap;">${tags}</div>`);
              }
          },
          {
              id: 'status_combined',
              name: 'Status',
              sort: false,
              width: '40px',
              formatter: (cell, row) => {
                  // Get the web value from hidden cell (shifted by 1 due to checkbox and has_infinite_client column)
                  const web = row.cells[6].data;      // web is at index 6 (shifted +1)
                  if (YS_DATA_SETTINGS.enableNotebook) {
                  const jupyter = row.cells[7].data;  // jupyter_status is at index 7 (shifted +1)
                  }
                
                  const webColor = web === 'Loaded' ? '#28a745' : '#6c757d';
                  if (YS_DATA_SETTINGS.enableNotebook) {
                  const jupyterColor = jupyter === 'Active' ? '#28a745' : '#6c757d';
                  }
                
                  return gridjs.html(`
                      <div class="status-indicators">
                          <span class="status-dot" style="background-color: ${webColor};" title="Web: ${web}"></span>
                          if (YS_DATA_SETTINGS.enableNotebook) {
                          <span class="status-dot" style="background-color: ${jupyterColor};" title="Lab: ${jupyter}"></span>
                          }
                      </div>
                  `);
              }
          },
          { id: 'web', hidden: true },
          if (YS_DATA_SETTINGS.enableNotebook) {
          { id: 'jupyter_status', hidden: true },
          }
          {
              id: 'details',
              name: '',
              sort: false,
              width: '45px',
              formatter: (cell, row) => {
                  const id = row.cells[0].data;
                  return gridjs.html(`
                      <div style="display: flex; flex-direction: column; gap: 3px; align-items: center;">
                          <a href="/admin/experiment_details/${id}"
                             style="background-color: #28a745; color: white; padding: 3px 6px; border-radius: 3px; text-decoration: none; font-size: 0.7rem; width: 100%; text-align: center;">
                              View
                          </a>
                          <a href="/admin/delete_simulation/${id}"
                             style="background-color: #dc3545; color: white; padding: 3px 6px; border-radius: 3px; text-decoration: none; font-size: 0.7rem; width: 100%; text-align: center;">
                              Delete
                          </a>
                      </div>
                  `);
              }
          },
      ];
  }

  // Create table for a specific status
  // Function to toggle group visibility
  function toggleGroup(groupId) {
      const content = document.getElementById(`content-${groupId}`);
      const chevron = document.getElementById(`chevron-${groupId}`);
    
      if (content.classList.contains('collapsed')) {
          content.classList.remove('collapsed');
          chevron.classList.remove('collapsed');
      } else {
          content.classList.add('collapsed');
          chevron.classList.add('collapsed');
      }
  }

  // Pagination state for each container
  const paginationState = {};

  // Function to download all experiments from a group
  function downloadGroupExperiments(groupName, statusFilter) {
      // Fetch all experiments in this group
      fetch(`/admin/experiments_data?exp_status=${statusFilter}&length=1000`)
          .then(response => response.json())
          .then(results => {
              const groupExps = results.data.filter(exp => 
                  (exp.exp_group || 'No group') === groupName
              );
            
              if (groupExps.length === 0) {
                  alert('No experiments found in this group.');
                  return;
              }
            
              const expIds = groupExps.map(exp => exp.idexp);
            
              // Submit form to download
              const form = document.createElement('form');
              form.method = 'POST';
              form.action = '/admin/download_experiments_bulk';
            
              const input = document.createElement('input');
              input.type = 'hidden';
              input.name = 'exp_ids';
              input.value = JSON.stringify(expIds);
              form.appendChild(input);
            
              document.body.appendChild(form);
              form.submit();
              document.body.removeChild(form);
          })
          .catch(error => {
              console.error('Error downloading group:', error);
              alert('Error downloading group experiments.');
          });
  }

  function submitBulkDelete(expIds, buttonId, loadingText) {
      if (!expIds || expIds.length === 0) {
          alert('No experiments found to delete.');
          return;
      }

      const btn = buttonId ? document.getElementById(buttonId) : null;
      let originalText = null;
      if (btn) {
          originalText = btn.innerHTML;
          btn.innerHTML = `<i class="mdi mdi-loading mdi-spin"></i> ${loadingText}`;
          btn.disabled = true;
      }

      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/admin/delete_simulations_bulk';

      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'exp_ids';
      input.value = JSON.stringify(expIds);
      form.appendChild(input);

      document.body.appendChild(form);
      form.submit();
      document.body.removeChild(form);

      if (btn) {
          setTimeout(() => {
              btn.innerHTML = originalText;
              btn.disabled = false;
          }, 1500);
      }
  }

  function deleteAllExperiments(statusFilter, buttonId, label) {
      fetch(`/admin/experiments_data?exp_status=${statusFilter}&length=1000`)
          .then(response => response.json())
          .then(results => {
              const expIds = (results.data || []).map(exp => exp.idexp);
              if (expIds.length === 0) {
                  alert(`No ${label} experiments found.`);
                  return;
              }

              if (!confirm(`Delete all ${expIds.length} ${label} experiments? This action cannot be undone.`)) {
                  return;
              }

              submitBulkDelete(expIds, buttonId, 'Deleting...');
          })
          .catch(error => {
              console.error('Error deleting all experiments:', error);
              alert('Error deleting experiments.');
          });
  }

  // Function to delete all experiments from a group
  function deleteGroupExperiments(groupName, statusFilter) {
      fetch(`/admin/experiments_data?exp_status=${statusFilter}&length=1000`)
          .then(response => response.json())
          .then(results => {
              const groupExps = results.data.filter(exp =>
                  (exp.exp_group || 'No group') === groupName
              );

              if (groupExps.length === 0) {
                  alert('No experiments found in this group.');
                  return;
              }

              if (!confirm(`Delete all ${groupExps.length} experiments in group "${groupName}"? This action cannot be undone.`)) {
                  return;
              }

              const expIds = groupExps.map(exp => exp.idexp);
              submitBulkDelete(expIds, null, 'Deleting...');
          })
          .catch(error => {
              console.error('Error deleting group:', error);
              alert('Error deleting group experiments.');
          });
  }

  // Function to create grouped experiment display with pagination
  function getVisibleExperimentBoxCount() {
      const boxes = ['box-active', 'box-completed', 'box-stopped'];
      return boxes
          .map(id => document.getElementById(id))
          .filter(box => box && getComputedStyle(box).display !== 'none').length;
  }

  function createGroupedView(containerId, statusFilter, boxId) {
      const containerDiv = document.getElementById(containerId);
      const boxDiv = document.getElementById(boxId);
    
      // Initialize pagination state if not exists
      if (!paginationState[containerId]) {
          paginationState[containerId] = { page: 0, itemsPerPage: 10 };
      }
    
      const state = paginationState[containerId];
    
      // Fetch experiments for this status
      fetch(`/admin/experiments_data?exp_status=${statusFilter}&length=1000`)
          .then(response => response.json())
          .then(results => {
              if (results.total === 0) {
                  boxDiv.style.display = 'none';
                  return;
              }
            
              boxDiv.style.display = 'flex';
            
              // Group experiments by exp_group
              const grouped = {};
              results.data.forEach(exp => {
                  const group = exp.exp_group || 'No group';
                  if (!grouped[group]) {
                      grouped[group] = [];
                  }
                  grouped[group].push(exp);
              });
            
              // Sort groups alphabetically
              const sortedGroups = Object.keys(grouped).sort();
            
              // Apply pagination to groups
              const totalGroups = sortedGroups.length;
              const startIdx = state.page * state.itemsPerPage;
              const endIdx = Math.min(startIdx + state.itemsPerPage, totalGroups);
              const paginatedGroups = sortedGroups.slice(startIdx, endIdx);
              const totalPages = Math.ceil(totalGroups / state.itemsPerPage);
            
              // Build HTML
              let html = '';
              paginatedGroups.forEach(group => {
                  const groupId = `${statusFilter}-${group.replace(/[^a-zA-Z0-9]/g, '_')}`;
                  const experiments = grouped[group];
                  const count = experiments.length;
                  const iconOnlyCompletedGroupActions =
                      statusFilter === EXP_STATUS.COMPLETED && getVisibleExperimentBoxCount() > 2;
                
                  // Determine badge color
                  let badgeClass = '';
                  if (statusFilter === EXP_STATUS.COMPLETED) badgeClass = 'completed';
                  else if (statusFilter === EXP_STATUS.STOPPED_SCHEDULED) badgeClass = 'stopped';
                
                  // Group header controls
                  const downloadBtn = statusFilter === EXP_STATUS.COMPLETED ? 
                      `<button onclick="event.stopPropagation(); downloadGroupExperiments('${group.replace(/'/g, "\\'")}', '${statusFilter}')" 
                               class="download-group-btn ${iconOnlyCompletedGroupActions ? 'group-action-icononly' : ''}"
                               title="Download all experiments in this group">
                          <i class="mdi mdi-download"></i><span class="group-btn-label">${iconOnlyCompletedGroupActions ? '' : ' Download Group'}</span>
                      </button>` : '';
                  const deleteBtn = statusFilter !== EXP_STATUS.ACTIVE ?
                      `<button onclick="event.stopPropagation(); deleteGroupExperiments('${group.replace(/'/g, "\\'")}', '${statusFilter}')" 
                               class="delete-group-btn ${iconOnlyCompletedGroupActions && statusFilter === EXP_STATUS.COMPLETED ? 'group-action-icononly' : ''}"
                               title="Delete all experiments in this group">
                          <i class="mdi mdi-delete"></i><span class="group-btn-label">${iconOnlyCompletedGroupActions && statusFilter === EXP_STATUS.COMPLETED ? '' : ' Delete Group'}</span>
                      </button>` : '';
                
                  // Determine if group should be collapsed by default (for completed and stopped)
                  const shouldCollapse = statusFilter !== EXP_STATUS.ACTIVE;
                  const collapsedClass = shouldCollapse ? ' collapsed' : '';
                
                  html += `
                      <div class="experiment-group">
                          <div class="group-header" onclick="toggleGroup('${groupId}')" 
                               style="border-left: 3px solid ${statusFilter === EXP_STATUS.ACTIVE ? '#28a745' : statusFilter === EXP_STATUS.COMPLETED ? '#17a2b8' : '#6c757d'}">
                              <div class="group-header-main">
                                  <i class="mdi mdi-chevron-down chevron${collapsedClass}" id="chevron-${groupId}"></i>
                                  <span class="group-header-title">${group}</span>
                                  <span class="count-badge ${badgeClass}">${count}</span>
                              </div>
                              <div class="group-header-actions">${downloadBtn}${deleteBtn}</div>
                              <span class="group-header-hint">Click to expand/collapse</span>
                          </div>
                          <div id="content-${groupId}" class="group-content${collapsedClass}">
                  `;
                
                  // Add experiments
                  experiments.forEach(exp => {
                      // Add checkbox for completed experiments
                      const checkbox = statusFilter === EXP_STATUS.COMPLETED ? 
                          `<input type="checkbox" class="exp-checkbox" data-exp-id="${exp.idexp}" 
                                  onchange="toggleExperimentSelection(${exp.idexp}, this)" 
                                  ${selectedExperiments.has(exp.idexp) ? 'checked' : ''}
                                  style="margin-right: 8px;" title="Select for download"/>` : '';
                    
                      html += `
                          <div class="exp-item" style="flex-direction: column; align-items: stretch;">
                              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                                  <div class="exp-item-info">
                                      ${checkbox}
                                      <span class="exp-item-name">${exp.exp_name}</span>
                                      <span class="exp-tag owner">${exp.owner}</span>
                                      <span class="exp-tag platform">${exp.platform_type === 'forum' ? 'Forum' : 'Microblogging'}</span>
                                      ${exp.simulator_type === 'HPC' ? '<span class="exp-tag hpc">HPC</span>' : ''}
                                      ${exp.is_remote === 1 ? '<span class="exp-tag remote">Remote</span>' : ''}
                                      ${exp.has_infinite_client ? '<span class="exp-tag infinite">∞</span>' : ''}
                                      ${statusFilter === EXP_STATUS.ACTIVE && exp.progress !== undefined ? `<span class="exp-tag" style="background: #039be5;">${exp.progress}%</span>` : ''}
                                  </div>
                                  <div style="display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; flex-shrink: 0; max-width: 100%;">
                                      ${exp.running === 'Running' ? 
                                          (exp.can_manage ? `<a href="#" onclick="stopExperimentServer(${exp.idexp}); return false;" title="Stop Server"><i class="mdi mdi-stop" style="font-size: 18px; color: #dc3545;"></i></a>` : '') : 
                                          `<a href="#" onclick="startExperimentServer(${exp.idexp}); return false;" title="Start Server"><i class="mdi mdi-play-box-outline" style="font-size: 18px; color: #28a745;"></i></a>`
                                      }
                                      ${exp.web === 'Loaded' ? 
                                          `<a href="/admin/select_experiment/${exp.idexp}" title="Loaded (click to unload)"><i class="mdi mdi-select-all" style="font-size: 18px; color: #28a745;"></i></a>` : 
                                          `<a href="/admin/select_experiment/${exp.idexp}" title="Load Web Interface"><i class="mdi mdi-select-all" style="font-size: 18px; color: #6c757d;"></i></a>`
                                      }
                                      <a href="/admin/experiment_details/${exp.idexp}" title="View Details"><i class="mdi mdi-open-in-new" style="font-size: 18px; color: #039be5;"></i></a>
                                      ${exp.can_manage ? `<a href="/admin/delete_simulation/${exp.idexp}" onclick="return confirm('Delete this experiment?')" title="Delete"><i class="mdi mdi-delete" style="font-size: 18px; color: #dc3545;"></i></a>` : ''}
                                  </div>
                              </div>
                              ${statusFilter === EXP_STATUS.ACTIVE ? `<div id="progress-section-${exp.idexp}" class="client-progress-section" style="display: none;"></div>` : ''}
                          </div>
                      `;
                  });
                
                  html += `
                          </div>
                      </div>
                  `;
              });
            
              // Add pagination controls if there are multiple pages
              if (totalPages > 1) {
                  html += `
                      <div class="pagination-container">
                          <div class="pagination-info">
                              Showing groups ${startIdx + 1}-${endIdx} of ${totalGroups}
                          </div>
                          <div class="pagination-buttons">
                              <button onclick="changePage('${containerId}', ${state.page - 1})" 
                                      ${state.page === 0 ? 'disabled' : ''}>
                                  <i class="mdi mdi-chevron-left"></i> Previous
                              </button>
                              <span style="padding: 4px 10px;">Page ${state.page + 1} of ${totalPages}</span>
                              <button onclick="changePage('${containerId}', ${state.page + 1})" 
                                      ${state.page >= totalPages - 1 ? 'disabled' : ''}>
                                  Next <i class="mdi mdi-chevron-right"></i>
                              </button>
                          </div>
                      </div>
                  `;
              }
            
              containerDiv.innerHTML = html;
            
              // For active experiments, fetch and display client progress bars
              if (statusFilter === EXP_STATUS.ACTIVE) {
                  results.data.forEach(exp => {
                      if (exp.running === 'Running') {
                          fetchAndDisplayClientProgress(exp.idexp);
                      }
                  });
              }
            
              // Update download button visibility after rendering
              updateDownloadButton();
          })
          .catch(error => {
              console.error('Error fetching experiments:', error);
              boxDiv.style.display = 'none';
          });
  }

  // Function to change pagination page
  function changePage(containerId, newPage) {
      if (!paginationState[containerId]) return;
      paginationState[containerId].page = newPage;
    
      // Determine which status this container belongs to
      let statusFilter;
      if (containerId === 'groups-active') statusFilter = EXP_STATUS.ACTIVE;
      else if (containerId === 'groups-completed') statusFilter = EXP_STATUS.COMPLETED;
      else if (containerId === 'groups-stopped') statusFilter = EXP_STATUS.STOPPED_SCHEDULED;
    
      const boxId = containerId.replace('groups-', 'box-');
      createGroupedView(containerId, statusFilter, boxId);
  }

  // Store active progress poll intervals
  const progressPollIntervals = {};

  // Store experiment-level sync intervals (for updating Client_Execution from logs)
  const experimentSyncIntervals = {};

  // Function to fetch and display client progress for an experiment
  function fetchAndDisplayClientProgress(expId) {
      const progressSection = document.getElementById(`progress-section-${expId}`);
      if (!progressSection) return;
    
      // Clear any existing experiment sync interval for this experiment
      if (experimentSyncIntervals[expId]) {
          clearInterval(experimentSyncIntervals[expId]);
          delete experimentSyncIntervals[expId];
      }
    
      // Function to fetch and update client data
      const fetchClientData = () => {
          const progressSection = document.getElementById(`progress-section-${expId}`);
          if (!progressSection) {
              // Progress section no longer exists, stop syncing
              if (experimentSyncIntervals[expId]) {
                  clearInterval(experimentSyncIntervals[expId]);
                  delete experimentSyncIntervals[expId];
              }
              return;
          }
        
          // Fetch client data for this experiment
          // This endpoint updates Client_Execution from log files on the backend
          fetch(`/admin/experiment_clients/${expId}`)
              .then(response => response.json())
              .then(data => {
                  if (data.error || !data.clients || data.clients.length === 0) {
                      progressSection.style.display = 'none';
                      return;
                  }
                
                  progressSection.style.display = 'block';
                  let html = '';
                
                  data.clients.forEach(client => {
                      if (client.status === 1) {  // Only show running clients
                          const progressId = `progress-${expId}-${client.id}`;
                          html += `
                              <div class="client-progress-item">
                                  <span class="client-name">${client.name}</span>
                                  <div class="sleek-progress-container">
                                      <div id="${progressId}" class="sleek-progress-bar" style="width: 0%;">
                                          <span>0%</span>
                                      </div>
                                  </div>
                              </div>
                          `;
                      }
                  });
                
                  if (html) {
                      progressSection.innerHTML = html;
                    
                      // Start polling for each running client
                      data.clients.forEach(client => {
                          if (client.status === 1) {
                              pollClientProgress(expId, client.id);
                          }
                      });
                  } else {
                      progressSection.style.display = 'none';
                  }
              })
              .catch(err => {
                  console.error('Error fetching client data:', err);
                  progressSection.style.display = 'none';
              });
      };
    
      // Initial fetch
      fetchClientData();
    
      // Set up interval to sync every 30 seconds
      // This ensures Client_Execution table is updated regularly from log files
      experimentSyncIntervals[expId] = setInterval(fetchClientData, 30000);
  }

  // Function to poll a single client's progress
  function pollClientProgress(expId, clientId) {
      const progressId = `progress-${expId}-${clientId}`;
      const intervalKey = `${expId}-${clientId}`;
    
      // Clear any existing interval for this client
      if (progressPollIntervals[intervalKey]) {
          clearInterval(progressPollIntervals[intervalKey]);
      }
    
      // Function to update progress
      const updateProgress = () => {
          const progressBar = document.getElementById(progressId);
          if (!progressBar) {
              // Progress bar no longer exists, stop polling
              if (progressPollIntervals[intervalKey]) {
                  clearInterval(progressPollIntervals[intervalKey]);
                  delete progressPollIntervals[intervalKey];
              }
              return;
          }
        
          fetch(`/admin/progress/${clientId}`)
              .then(response => {
                  if (!response.ok) {
                      throw new Error(`HTTP ${response.status}`);
                  }
                  return response.json();
              })
              .then(data => {
                  if (data.infinite) {
                      // Infinite client - show green bar with elapsed time
                      progressBar.style.width = '100%';
                      progressBar.style.background = 'linear-gradient(90deg, #22c55e 0%, #4ade80 100%)';
                      progressBar.style.boxShadow = '0 2px 6px rgba(34,197,94,0.3)';
                    
                      const days = data.elapsed_days || 0;
                      const hours = data.elapsed_hours || 0;
                      let timeText = '';
                      if (days > 0) {
                          timeText = days + 'd ' + hours + 'h';
                      } else {
                          timeText = hours + 'h';
                      }
                      progressBar.querySelector('span').textContent = '∞ ' + timeText;
                  } else {
                      // Finite client - show progress percentage
                      const percentage = Math.min(100, Math.max(0, data.progress || 0));
                      progressBar.style.width = percentage + '%';
                      progressBar.querySelector('span').textContent = percentage + '%';
                    
                      // Update gradient based on progress
                      if (percentage >= 75) {
                          progressBar.style.background = 'linear-gradient(90deg, #039be5 0%, #00d1b2 100%)';
                          progressBar.style.boxShadow = '0 2px 6px rgba(0,209,178,0.3)';
                      } else if (percentage >= 50) {
                          progressBar.style.background = 'linear-gradient(90deg, #039be5 0%, #5596e6 100%)';
                          progressBar.style.boxShadow = '0 2px 6px rgba(85,150,230,0.3)';
                      }
                  }
              })
              .catch(err => console.error('Error polling progress:', err));
      };
    
      // Initial update
      updateProgress();
    
      // Poll every 2 seconds
      progressPollIntervals[intervalKey] = setInterval(updateProgress, 2000);
  }

  // Function to refresh all grouped views
  function refreshAllTables() {
      // Clean up old progress poll intervals when refreshing
      // (they will be recreated for visible experiments)
      Object.keys(progressPollIntervals).forEach(key => {
          clearInterval(progressPollIntervals[key]);
          delete progressPollIntervals[key];
      });
    
      // Clean up experiment sync intervals
      Object.keys(experimentSyncIntervals).forEach(key => {
          clearInterval(experimentSyncIntervals[key]);
          delete experimentSyncIntervals[key];
      });
    
      createGroupedView('groups-active', EXP_STATUS.ACTIVE, 'box-active');
      createGroupedView('groups-completed', EXP_STATUS.COMPLETED, 'box-completed');
      createGroupedView('groups-stopped', EXP_STATUS.STOPPED_SCHEDULED, 'box-stopped');
  }

  // Create all three grouped views using status constants
  createGroupedView('groups-active', EXP_STATUS.ACTIVE, 'box-active');
  createGroupedView('groups-completed', EXP_STATUS.COMPLETED, 'box-completed');
  createGroupedView('groups-stopped', EXP_STATUS.STOPPED_SCHEDULED, 'box-stopped');

  // Clean up progress polling intervals when page unloads
  window.addEventListener('beforeunload', () => {
      Object.keys(progressPollIntervals).forEach(key => {
          clearInterval(progressPollIntervals[key]);
          delete progressPollIntervals[key];
      });
  });

  // Delay for Grid.js to complete rendering before equalizing heights
  const EQUALIZATION_DELAY = 500;

  // Function to equalize heights of visible experiment boxes
  function equalizeBoxHeights() {
      const boxes = ['box-active', 'box-completed', 'box-stopped'];
      const visibleBoxes = boxes.map(id => document.getElementById(id))
          .filter(box => box && getComputedStyle(box).display !== 'none');
    
      if (visibleBoxes.length <= 1) return;
    
      // Reset heights to auto to get natural heights
      visibleBoxes.forEach(box => box.style.height = 'auto');
    
      // Wait a frame for layout recalculation
      requestAnimationFrame(() => {
          // Find the maximum height
          const maxHeight = Math.max(...visibleBoxes.map(box => box.offsetHeight));
        
          // Apply the maximum height to all visible boxes
          visibleBoxes.forEach(box => {
              box.style.height = maxHeight + 'px';
          });
      });
  }

  // Equalize heights after initial tables load (with delay for Grid.js render)
  // setTimeout(equalizeBoxHeights, EQUALIZATION_DELAY);  // No longer needed with grouped views

  // Also equalize after each refresh - no longer needed
  /* if (typeof refreshAllTables === 'function') {
      const originalRefreshAllTables = refreshAllTables;
      refreshAllTables = function() {
          originalRefreshAllTables();
          // Re-equalize after the async refresh completes
          setTimeout(equalizeBoxHeights, EQUALIZATION_DELAY);
      };
  } */

  // Set up periodic refresh
  setInterval(refreshAllTables, DATA_REFRESH_INTERVAL);

  let savedValue;

  // Inline editing support for all tables (using document-level delegation)
  document.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD' && ev.target.hasAttribute('data-element-id')) {
          savedValue = ev.target.textContent;
      }
  });

  document.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.hasAttribute('data-element-id')) {
          if (savedValue !== ev.target.textContent) {
              fetch('/admin/experiments_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue = undefined;
      }
  });

  document.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD' && ev.target.hasAttribute('data-element-id')) {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  // Handle Delete Button
  document.addEventListener('click', function (event) {
      const target = event.target;
      if (target.classList.contains('delete-button')) {
          const id = target.getAttribute('data-id');
          if (confirm('Are you sure you want to delete this experiment?')) {
              fetch(`/admin/delete_simulation/${id}`, {
                  method: 'DELETE',
              })
              .then(response => {
                  if (!response.ok) throw new Error('Failed to delete');
                  // Refresh table after deletion
                  location.reload();
              })
              .catch(err => {
                  alert('Error deleting experiment.');
                  console.error(err);
              });
          }
      }
  });

  let scheduleCheckInterval = null;
  let currentRunningGroupId = null;

  // Load schedule data on page load
  document.addEventListener('DOMContentLoaded', function() {
      loadAvailableExperiments();
      loadScheduleGroups();
      loadPersistentLogs();
      checkScheduleStatus();
  });

  function loadPersistentLogs() {
      fetch('/admin/schedule/logs')
          .then(response => response.json())
          .then(data => {
              const logDiv = document.getElementById('schedule-log');
              if (logDiv && data.logs && data.logs.length > 0) {
                  logDiv.innerHTML = data.logs.map(log => {
                      const timestamp = log.created_at ? new Date(log.created_at).toLocaleTimeString() : '';
                      const colorClass = log.log_type === 'success' ? 'color: #28a745;' : 
                                         log.log_type === 'error' ? 'color: #dc3545;' :
                                         log.log_type === 'warning' ? 'color: #ffc107;' : '';
                      return `<div><span style="color: #6c757d;">[${timestamp}]</span> <span style="${colorClass}">${log.message}</span></div>`;
                  }).join('');
                  logDiv.scrollTop = logDiv.scrollHeight;
              } else if (logDiv) {
                  logDiv.innerHTML = '<p style="color: #999; text-align: center; margin: 0;">No logs yet</p>';
              }
          })
          .catch(err => console.error('Error loading logs:', err));
  }

  function clearLogs() {
      fetch('/admin/schedule/logs/clear', { method: 'POST' })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  const logDiv = document.getElementById('schedule-log');
                  if (logDiv) {
                      logDiv.innerHTML = '<p style="color: #999; text-align: center; margin: 0;">No logs yet</p>';
                  }
              }
          })
          .catch(err => console.error('Error clearing logs:', err));
  }

  function autoCreateGroups() {
      const inputField = document.getElementById('exps-per-group');
      const experimentsPerGroup = parseInt(inputField ? inputField.value : 2);
    
      if (isNaN(experimentsPerGroup) || experimentsPerGroup < 1) {
          alert('Please enter a valid number (1 or more)');
          return;
      }

      // Get selected group from the dropdown (single selection)
      const groupFilter = document.getElementById('group-filter');
      const selectedGroup = groupFilter.value;

      fetch('/admin/schedule/auto_create_groups', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
              experiments_per_group: experimentsPerGroup,
              group_filter: selectedGroup && selectedGroup !== '' ? [selectedGroup] : null
          })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              loadScheduleGroups();
              loadAvailableExperiments();
              loadPersistentLogs();
          } else {
              alert(data.message || 'Failed to create groups');
          }
      })
      .catch(err => alert('Error creating groups'));
  }

  function loadAvailableExperiments() {
      fetch('/admin/schedule/available_experiments')
          .then(response => response.json())
          .then(data => {
              const container = document.getElementById('available-experiments');
              if (!container) return;
              if (data.experiments && data.experiments.length > 0) {
                  container.innerHTML = data.experiments.map(exp => `
                      <div class="draggable-experiment" draggable="true" data-exp-id="${exp.id}" 
                           style="padding: 8px 10px; margin: 4px 0; background: #f8f9fa; border: 1px solid #dee2e6; 
                                  border-radius: 4px; cursor: grab; font-size: 0.85em; display: flex; justify-content: space-between; align-items: center;"
                           ondragstart="handleDragStart(event)">
                           <span><strong>${exp.name}</strong> <span style="color: #6c757d;">(${exp.owner})</span></span>
                      </div>
                  `).join('');
              } else {
                  container.innerHTML = '<p style="color: #999; font-size: 0.85em; text-align: center; padding: 20px;">No available experiments</p>';
              }
          })
          .catch(err => console.error('Error loading experiments:', err));
  }

  function loadScheduleGroups() {
      fetch('/admin/schedule/groups')
          .then(response => response.json())
          .then(data => {
              const container = document.getElementById('schedule-groups');
              if (!container) return;
              if (data.groups && data.groups.length > 0) {
                  container.innerHTML = data.groups.map((group, idx) => {
                      const isRunning = currentRunningGroupId === group.id;
                      const headerBg = isRunning ? '#28a745' : '#e9ecef';
                      const headerColor = isRunning ? 'white' : 'inherit';
                      const borderColor = isRunning ? '#28a745' : '#dee2e6';
                      const runningBadge = isRunning ? '<span style="background: white; color: #28a745; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; margin-left: 8px;">RUNNING</span>' : '';
                    
                      // Filter out completed experiments from running group display
                      const activeExperiments = isRunning 
                          ? group.experiments.filter(exp => exp.exp_status !== 'completed')
                          : group.experiments;
                    
                      // Count completed experiments for display
                      const completedCount = isRunning 
                          ? group.experiments.filter(exp => exp.exp_status === 'completed').length
                          : 0;
                      const completedBadge = completedCount > 0 
                          ? `<span style="background: #17a2b8; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; margin-left: 4px;">${completedCount} done</span>` 
                          : '';
                    
                      return `
                      <div class="schedule-group" data-group-id="${group.id}" 
                           style="margin-bottom: 15px; border: 2px solid ${borderColor}; border-radius: 6px; background: #fff; ${isRunning ? 'box-shadow: 0 0 10px rgba(40, 167, 69, 0.3);' : ''}">
                          <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 4px; padding: 8px 12px; background: ${headerBg}; color: ${headerColor}; border-radius: 4px 4px 0 0;">
                              <span style="font-weight: 600; font-size: 0.85em; display: flex; flex-wrap: wrap; align-items: center; gap: 4px;">
                                  <i class="mdi mdi-numeric-${idx + 1}-circle" style="color: ${isRunning ? 'white' : '#6c757d'};"></i> 
                                  ${group.name}
                                  ${runningBadge}
                                  ${completedBadge}
                              </span>
                              <button onclick="deleteScheduleGroup(${group.id})" style="background: none; border: none; color: ${isRunning ? 'rgba(255,255,255,0.7)' : '#dc3545'}; cursor: ${isRunning ? 'not-allowed' : 'pointer'}; font-size: 1em;" ${isRunning ? 'disabled title="Cannot delete running group"' : ''}>
                                  <i class="mdi mdi-delete"></i>
                              </button>
                          </div>
                          <div class="group-experiments" data-group-id="${group.id}" 
                               style="min-height: 50px; padding: 8px; background: ${isRunning ? '#f0fff4' : '#fafafa'}; display: flex; flex-wrap: wrap; gap: 6px; align-items: flex-start;"
                               ondragover="handleDragOver(event)" ondrop="handleDrop(event, ${group.id})">
                              ${activeExperiments.length > 0 ? activeExperiments.map(exp => `
                                  <span class="experiment-tag" style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; background: ${isRunning ? '#28a745' : '#6c757d'}; color: white; border-radius: 15px; font-size: 0.75em; white-space: nowrap;">
                                      <i class="mdi mdi-flask"></i>
                                      ${exp.name}
                                      ${!isRunning ? `<button onclick="removeExperimentFromGroup(${exp.item_id})" style="background: none; border: none; color: rgba(255,255,255,0.8); cursor: pointer; padding: 0; margin-left: 4px; font-size: 1.1em; line-height: 1;">
                                          <i class="mdi mdi-close-circle"></i>
                                      </button>` : ''}
                                  </span>
                              `).join('') : (isRunning && completedCount > 0 ? '<p style="color: #28a745; font-size: 0.8em; text-align: center; margin: 0; width: 100%;"><i class="mdi mdi-check-circle"></i> All experiments completed!</p>' : '<p style="color: #999; font-size: 0.8em; text-align: center; margin: 0; width: 100%;">Drag experiments here</p>')}
                          </div>
                      </div>
                  `}).join('');
              } else {
                  container.innerHTML = '<p style="color: #999; font-size: 0.85em; text-align: center; padding: 20px;">No groups created yet. Click "Add Group" to start.</p>';
              }
          })
          .catch(err => console.error('Error loading groups:', err));
  }

  function addScheduleGroup() {
      // Auto-generate incremental group name
      const container = document.getElementById('schedule-groups-container');
      const existingGroups = container ? container.querySelectorAll('.schedule-group').length : 0;
      const name = 'Group ' + (existingGroups + 1);

      fetch('/admin/schedule/groups', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              loadScheduleGroups();
          } else {
              alert(data.message || 'Failed to create group');
          }
      })
      .catch(err => alert('Error creating group'));
  }

  function deleteScheduleGroup(groupId) {
      if (currentRunningGroupId === groupId) {
          alert('Cannot delete a running group. Stop the schedule first.');
          return;
      }

      fetch(`/admin/schedule/groups/${groupId}`, { method: 'DELETE' })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  loadScheduleGroups();
                  loadAvailableExperiments();
              } else {
                  alert(data.message || 'Failed to delete group');
              }
          })
          .catch(err => console.error('Error deleting group:', err));
  }

  function handleDragStart(event) {
      event.dataTransfer.setData('text/plain', event.target.dataset.expId);
      event.target.style.opacity = '0.5';
  }

  function handleDragOver(event) {
      event.preventDefault();
      event.currentTarget.style.background = '#e8f4e8';
  }

  function handleDrop(event, groupId) {
      event.preventDefault();
      event.currentTarget.style.background = currentRunningGroupId === groupId ? '#f0fff4' : '#fafafa';
    
      const expId = event.dataTransfer.getData('text/plain');
      if (!expId) return;

      fetch(`/admin/schedule/groups/${groupId}/experiments`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ experiment_id: parseInt(expId) })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              loadScheduleGroups();
              loadAvailableExperiments();
          } else {
              alert(data.message || 'Failed to add experiment');
          }
      })
      .catch(err => alert('Error adding experiment to group'));
  }

  function removeExperimentFromGroup(itemId) {
      fetch(`/admin/schedule/items/${itemId}`, { method: 'DELETE' })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  loadScheduleGroups();
                  loadAvailableExperiments();
              } else {
                  alert(data.message || 'Cannot remove experiment');
              }
          })
          .catch(err => console.error('Error removing experiment:', err));
  }

  function addLogMessage(message) {
      const logDiv = document.getElementById('schedule-log');
      if (!logDiv) return;
      // Clear "No logs yet" placeholder if present
      if (logDiv.querySelector('p')) {
          logDiv.innerHTML = '';
      }
    
      const timestamp = new Date().toLocaleTimeString();
      const msgDiv = document.createElement('div');
      msgDiv.innerHTML = `<span style="color: #6c757d;">[${timestamp}]</span> ${message}`;
      logDiv.appendChild(msgDiv);
      logDiv.scrollTop = logDiv.scrollHeight;
  }

  function displayLogs(logs) {
      if (logs && logs.length > 0) {
          logs.forEach(log => addLogMessage(log));
      }
  }

  function startSchedule() {
      // Clear previous logs display
      const logDiv = document.getElementById('schedule-log');
      if (logDiv) {
          logDiv.innerHTML = '';
          addLogMessage('Starting schedule...');
      }

      fetch('/admin/schedule/start', { method: 'POST' })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  // Reload persistent logs after start
                  loadPersistentLogs();
                  currentRunningGroupId = data.current_group_id;
                  checkScheduleStatus();
                  loadScheduleGroups();
                  // Start polling for progress
                  scheduleCheckInterval = setInterval(checkScheduleProgress, 30000);
              } else {
                  addLogMessage(`<strong style="color: #dc3545;">✗ ${data.message}</strong>`);
              }
          })
          .catch(err => {
              addLogMessage(`<strong style="color: #dc3545;">✗ Error starting schedule</strong>`);
          });
  }

  function stopSchedule() {
      if (!confirm('Stop the schedule? This will stop all running experiments.')) return;

      addLogMessage('Stopping schedule...');

      fetch('/admin/schedule/stop', { method: 'POST' })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  addLogMessage(`<strong style="color: #dc3545;">Schedule stopped</strong>`);
                  currentRunningGroupId = null;
                  checkScheduleStatus();
                  loadScheduleGroups();
                  if (scheduleCheckInterval) {
                      clearInterval(scheduleCheckInterval);
                  }
              } else {
                  addLogMessage(`<strong style="color: #dc3545;">✗ ${data.message}</strong>`);
              }
          })
          .catch(err => addLogMessage('<strong style="color: #dc3545;">✗ Error stopping schedule</strong>'));
  }

  function checkScheduleStatus() {
      fetch('/admin/schedule/status')
          .then(response => response.json())
          .then(data => {
              const startBtn = document.getElementById('start-schedule-btn');
              const stopBtn = document.getElementById('stop-schedule-btn');
              const badge = document.getElementById('schedule-status-badge');

              if (data.is_running) {
                  if (startBtn) startBtn.style.display = 'none';
                  if (stopBtn) stopBtn.style.display = 'inline-block';
                  if (badge) {
                      badge.style.display = 'inline-block';
                      badge.style.background = '#28a745';
                      badge.style.color = 'white';
                      badge.textContent = 'Running';
                  }
                  currentRunningGroupId = data.current_group_id;
                  // Start progress check if not already running
                  if (!scheduleCheckInterval) {
                      scheduleCheckInterval = setInterval(checkScheduleProgress, 30000);
                  }
              } else {
                  if (startBtn) startBtn.style.display = 'inline-block';
                  if (stopBtn) stopBtn.style.display = 'none';
                  if (badge) badge.style.display = 'none';
                  currentRunningGroupId = null;
                  if (scheduleCheckInterval) {
                      clearInterval(scheduleCheckInterval);
                      scheduleCheckInterval = null;
                  }
              }
              loadScheduleGroups();
          })
          .catch(err => console.error('Error checking status:', err));
  }

  function checkScheduleProgress() {
      fetch('/admin/schedule/check_progress', { method: 'POST' })
          .then(response => response.json())
          .then(data => {
              // Reload persistent logs to get latest
              loadPersistentLogs();
            
              // Always reload schedule groups to update completed experiment tags
              loadScheduleGroups();
            
              if (data.schedule_complete) {
                  if (scheduleCheckInterval) {
                      clearInterval(scheduleCheckInterval);
                      scheduleCheckInterval = null;
                  }
                  currentRunningGroupId = null;
                  checkScheduleStatus();
                  loadAvailableExperiments();
                  // Refresh DataTables to show updated statuses
                  refreshAllTables();
              } else if (data.next_group) {
                  currentRunningGroupId = data.next_group_id;
              }
          })
          .catch(err => console.error('Error checking progress:', err));
  }

                                          const tags = document.getElementById('tags');
  const input = document.getElementById('input-tag');
  const hiddenInput = document.getElementById('tags-hidden');
  const tagList = [];

  function updateButtonState() {
      const createBtn = document.getElementById('create-experiment-btn');
      if (createBtn) {
          if (tagList.length > 0) {
              createBtn.disabled = false;
          } else {
              createBtn.disabled = true;
          }
      }
  }

  input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
          event.preventDefault();
          const tagContent = input.value.trim();
          if (tagContent !== '' && !tagList.includes(tagContent)) {
              tagList.push(tagContent);
              const tag = document.createElement('li');
              tag.innerHTML = `${tagContent} <button class="delete-button">X</button>`;
              tags.appendChild(tag);
              hiddenInput.value = tagList.join(',');
              input.value = '';
              updateButtonState();
          }
      }
  });

  tags.addEventListener('click', function (event) {
      if (event.target.classList.contains('delete-button') && !event.target.disabled) {
          const tagText = event.target.parentNode.textContent.slice(0, -1).trim();
          tagList.splice(tagList.indexOf(tagText), 1);
          hiddenInput.value = tagList.join(',');
          event.target.parentNode.remove();
          updateButtonState();
      }
  });

  // Show/hide Perspective API field based on toxicity annotation toggle
  document.addEventListener('DOMContentLoaded', function() {
      const toxicityToggle = document.getElementById('toxicity_annotation_toggle');
      const perspectiveApiField = document.getElementById('perspective_api_field');
      const llmAgentsToggle = document.getElementById('llm_agents_toggle');
      const sentimentToggle = document.getElementById('sentiment_annotation_toggle');
      const emotionToggle = document.getElementById('emotion_annotation_toggle');
      const opinionToggle = document.getElementById('opinion_annotation_toggle');
      const annotationSettingsRow = document.getElementById('annotation_settings_row');
      const inputTag = document.getElementById('input-tag');

      toxicityToggle.addEventListener('change', function() {
          if (this.checked) {
              perspectiveApiField.style.display = 'flex';
          } else {
              perspectiveApiField.style.display = 'none';
          }
      });

      // Handle LLM agents toggle
      llmAgentsToggle.addEventListener('change', function() {
          const topicCountInput = document.getElementById('topic-count-input');
        
          if (!this.checked) {
              // Disable all annotation toggles
              toxicityToggle.checked = false;
              toxicityToggle.disabled = true;
              sentimentToggle.checked = false;
              sentimentToggle.disabled = true;
              emotionToggle.checked = false;
              emotionToggle.disabled = true;
              opinionToggle.checked = false;
              opinionToggle.disabled = true;
              perspectiveApiField.style.display = 'none';

              // Clear topics and show numeric input for topic count
              tagList.length = 0;
              while (tags.firstChild) {
                  tags.removeChild(tags.firstChild);
              }
            
              // Hide tag input, show topic count input first
              inputTag.style.display = 'none';
              topicCountInput.style.display = 'block';
            
              // Generate initial topics with default count (10)
              generateTopics(10);
              updateButtonState();
          } else {
              // Re-enable all annotation toggles
              const isForum = platformTypeSelect.value === 'forum';
              toxicityToggle.disabled = isForum;
              sentimentToggle.checked = !isForum;
              sentimentToggle.disabled = isForum;
              emotionToggle.checked = !isForum;
              emotionToggle.disabled = isForum;
              opinionToggle.checked = !isForum;
              opinionToggle.disabled = isForum;

              // Re-enable topics input and clear default
              tagList.length = 0;
              while (tags.firstChild) {
                  tags.removeChild(tags.firstChild);
              }
              hiddenInput.value = '';
              inputTag.style.display = 'block';
              inputTag.disabled = false;
              inputTag.placeholder = 'Enter topic name';
              topicCountInput.style.display = 'none';
              updateButtonState();
          }
          updateSimulatorTypeUI();
      });
    
      // Function to generate topics
      function generateTopics(count) {
          // Clear existing topics
          tagList.length = 0;
          while (tags.firstChild) {
              tags.removeChild(tags.firstChild);
          }
        
          // Generate new topics
          for (let i = 1; i <= count; i++) {
              const topicName = `Topic${i}`;
              tagList.push(topicName);
              const tag = document.createElement('li');
            
              // Create text node for topic name (prevents XSS)
              tag.textContent = topicName + ' ';
            
              // Create delete button separately
              const deleteBtn = document.createElement('button');
              deleteBtn.className = 'delete-button';
              deleteBtn.textContent = 'X';
              deleteBtn.disabled = true;
              deleteBtn.style.cursor = 'not-allowed';
              deleteBtn.style.opacity = '0.5';
            
              tag.appendChild(deleteBtn);
              tags.appendChild(tag);
          }
          hiddenInput.value = tagList.join(',');
          updateButtonState();
      }
    
      // Handle generate topics button click
      document.getElementById('generate-topics-btn').addEventListener('click', function() {
          const topicCount = parseInt(document.getElementById('topic-count').value);
          if (!isNaN(topicCount) && topicCount >= 1 && topicCount <= 100) {
              generateTopics(topicCount);
          }
      });

      const simulatorTypeInput = document.getElementById('simulator_type_input');
      const hpcToggle = document.getElementById('hpc_toggle');
      const hpcToggleLabel = document.getElementById('hpc-toggle-label');
      const hpcToggleContainer = document.getElementById('hpc-toggle-container');
      const hpcInfoInline = document.getElementById('hpc-info-inline');
      const redisConfigBox = document.getElementById('redis-config-box');
      const platformTypeSelect = document.getElementById('platform_type_select');
    
      // Handle Redis Configuration collapsible toggle
      const redisConfigHeader = document.getElementById('redis-config-header');
      const redisConfigContent = document.getElementById('redis-config-content');
      const redisConfigIcon = document.getElementById('redis-config-icon');
    
      redisConfigHeader.addEventListener('click', function() {
          const isExpanded = redisConfigContent.style.display === 'block';
          if (isExpanded) {
              redisConfigContent.style.display = 'none';
              redisConfigIcon.style.transform = 'rotate(0deg)';
          } else {
              redisConfigContent.style.display = 'block';
              redisConfigIcon.style.transform = 'rotate(180deg)';
          }
      });
    
      // Hover effect for Redis config header
      redisConfigHeader.addEventListener('mouseenter', function() {
          redisConfigHeader.style.background = '#f3f4f6';
      });
      redisConfigHeader.addEventListener('mouseleave', function() {
          redisConfigHeader.style.background = '#f9fafb';
      });

      function updateSimulatorTypeUI() {
          const isForum = platformTypeSelect.value === 'forum';
          const isHPC = !isForum && hpcToggle.checked;
          const remoteExperimentToggle = document.getElementById('remote_experiment_toggle');
          const remoteExperimentContainer = document.getElementById('remote-experiment-container');
          const remoteExperimentLabel = document.getElementById('remote-experiment-label');
          const llmEnabled = llmAgentsToggle.checked;

          simulatorTypeInput.value = isHPC ? 'HPC' : 'Standard';

          if (isForum) {
              hpcToggle.checked = false;
              hpcToggle.disabled = true;
              hpcToggleLabel.textContent = 'Unavailable for Forum';
              if (hpcToggleContainer) {
                  hpcToggleContainer.style.opacity = '0.55';
              }
          } else {
              hpcToggle.disabled = false;
              hpcToggleLabel.textContent = isHPC ? 'Enabled' : 'Disabled';
              if (hpcToggleContainer) {
                  hpcToggleContainer.style.opacity = '1';
              }
          }

          if (annotationSettingsRow) {
              annotationSettingsRow.style.display = isForum ? 'none' : 'flex';
          }

          if (isForum) {
              toxicityToggle.checked = false;
              toxicityToggle.disabled = true;
              sentimentToggle.checked = false;
              sentimentToggle.disabled = true;
              emotionToggle.checked = false;
              emotionToggle.disabled = true;
              opinionToggle.checked = false;
              opinionToggle.disabled = true;
              perspectiveApiField.style.display = 'none';
          } else {
              toxicityToggle.disabled = !llmEnabled;
              sentimentToggle.disabled = !llmEnabled;
              emotionToggle.disabled = !llmEnabled;
              opinionToggle.disabled = !llmEnabled;
              if (llmEnabled) {
                  sentimentToggle.checked = true;
                  emotionToggle.checked = true;
                  opinionToggle.checked = true;
              }
              if (toxicityToggle.checked && llmEnabled) {
                  perspectiveApiField.style.display = 'flex';
              } else {
                  perspectiveApiField.style.display = 'none';
              }
          }
        
          if (isHPC) {
              hpcInfoInline.style.display = 'block';
              redisConfigBox.style.display = 'flex';

              // Disable remote experiment toggle for HPC
              remoteExperimentToggle.disabled = true;
              remoteExperimentToggle.checked = false;
              if (remoteExperimentContainer) {
                  remoteExperimentContainer.style.opacity = '0.5';
                  remoteExperimentContainer.style.cursor = 'not-allowed';
              }
              if (remoteExperimentLabel) {
                  remoteExperimentLabel.style.color = '#9ca3af';
              }
              // Hide remote config box if it was visible
              const remoteConfigBox = document.getElementById('remote-config-box');
              if (remoteConfigBox) {
                  remoteConfigBox.style.display = 'none';
              }
              // Update required attributes
              const remoteHostInput = document.getElementById('remote_host');
              const remotePortInput = document.getElementById('remote_port');
              if (remoteHostInput) remoteHostInput.required = false;
              if (remotePortInput) remotePortInput.required = false;
          } else {
              hpcInfoInline.style.display = 'none';
              redisConfigBox.style.display = 'none';

              remoteExperimentToggle.disabled = false;
              if (remoteExperimentContainer) {
                  remoteExperimentContainer.style.opacity = '1';
                  remoteExperimentContainer.style.cursor = 'pointer';
              }
              if (remoteExperimentLabel) {
                  remoteExperimentLabel.style.color = '#6b7280';
              }
          }
      }

      hpcToggle.addEventListener('change', updateSimulatorTypeUI);
      platformTypeSelect.addEventListener('change', updateSimulatorTypeUI);
    
      // Initialize on page load
      updateSimulatorTypeUI();

      // Handle Remote Experiment toggle
      const remoteExperimentToggle = document.getElementById('remote_experiment_toggle');
      const remoteConfigBox = document.getElementById('remote-config-box');
      const remoteHostInput = document.getElementById('remote_host');
      const remotePortInput = document.getElementById('remote_port');

      remoteExperimentToggle.addEventListener('change', function() {
          if (this.checked) {
              remoteConfigBox.style.display = 'flex';
              remoteHostInput.required = true;
              remotePortInput.required = true;
          } else {
              remoteConfigBox.style.display = 'none';
              remoteHostInput.required = false;
              remotePortInput.required = false;
          }
      });
  });

  function displayExperimentFileName(input) {
      const display = document.getElementById('experiment-file-name-display');
      if (input.files && input.files[0]) {
          display.textContent = '✓ ' + input.files[0].name;
      } else {
          display.textContent = '';
      }
  }
})();
