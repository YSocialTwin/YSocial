/**
 * AdminPopulations - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminPopulations = (function() {
  const bindById = (id, eventName, handler) => {
      const element = document.getElementById(id);
      if (element) {
          element.addEventListener(eventName, handler);
      }
      return element;
  };

  const createChartIfPresent = (canvasId, config) => {
      const canvas = document.getElementById(canvasId);
      if (!canvas) {
          return null;
      }
      return new Chart(canvas, config);
  };

  const popDetails = window.YS_DATA_POP_DETAILS;

  if (popDetails) {
  createChartIfPresent("ages", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Age',
              data: popDetails.ages.data,
              backgroundColor: 'rgba(168, 85, 247, 0.7)',
              borderColor: 'rgba(168, 85, 247, 1)',
              borderWidth: 1
          }],
          labels: popDetails.ages.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Age Distribution',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { 
                      font: { size: 11 },
                      maxRotation: 45,
                      minRotation: 45
                  }
              }
          }
      }
  });

  createChartIfPresent("gender", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Gender',
              data: popDetails.gender.data,
              backgroundColor: 'rgba(139, 92, 246, 0.7)',
              borderColor: 'rgba(139, 92, 246, 1)',
              borderWidth: 1
          }],
          labels: popDetails.gender.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Gender Distribution',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  createChartIfPresent("nationalities", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Nationalities',
              data: popDetails.nationalities.data,
              backgroundColor: 'rgba(59, 130, 246, 0.7)',
              borderColor: 'rgba(59, 130, 246, 1)',
              borderWidth: 1
          }],
          labels: popDetails.nationalities.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Nationalities',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  createChartIfPresent("edu", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Education',
              data: popDetails.education.data,
              backgroundColor: 'rgba(236, 72, 153, 0.7)',
              borderColor: 'rgba(236, 72, 153, 1)',
              borderWidth: 1
          }],
          labels: popDetails.education.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Education Levels',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  createChartIfPresent("languages", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Spoken Languages',
              data: popDetails.languages.data,
              backgroundColor: 'rgba(234, 179, 8, 0.7)',
              borderColor: 'rgba(234, 179, 8, 1)',
              borderWidth: 1
          }],
          labels: popDetails.languages.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Spoken Languages',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  createChartIfPresent("leanings", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Political Leanings',
              data: popDetails.leanings.data,
              backgroundColor: 'rgba(34, 197, 94, 0.7)',
              borderColor: 'rgba(34, 197, 94, 1)',
              borderWidth: 1
          }],
          labels: popDetails.leanings.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Political Leanings',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  createChartIfPresent("tox", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Toxicity Levels',
              data: popDetails.toxicity.data,
              backgroundColor: 'rgba(239, 68, 68, 0.7)',
              borderColor: 'rgba(239, 68, 68, 1)',
              borderWidth: 1
          }],
          labels: popDetails.toxicity.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Toxicity Levels',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  createChartIfPresent("activity_profiles", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Activity Profiles',
              data: popDetails.activityProfiles.data,
              backgroundColor: 'rgba(99, 102, 241, 0.7)',
              borderColor: 'rgba(99, 102, 241, 1)',
              borderWidth: 1
          }],
          labels: popDetails.activityProfiles.labels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Activity Profiles Distribution',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });

  // Create word cloud effect using bar chart
  const profData = popDetails.professions.data;
  const profLabels = popDetails.professions.labels;

  // Take top 10 for readability
  const topCount = Math.min(10, profLabels.length);
  const topProfLabels = profLabels.slice(0, topCount);
  const topProfData = profData.slice(0, topCount);

  createChartIfPresent("professions", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Professions',
              data: topProfData,
              backgroundColor: 'rgba(16, 185, 129, 0.7)',
              borderColor: 'rgba(16, 185, 129, 1)',
              borderWidth: 1
          }],
          labels: topProfLabels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: 'y',
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Top Professions',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              x: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              y: {
                  ticks: { font: { size: 10 } }
              }
          }
      }
  });

  const activityLevels = popDetails.activity.levels;
  const activityLabels = activityLevels.map(level => {
      const labelMap = {
          1: 'Very Low',
          2: 'Low',
          3: 'Medium',
          4: 'High',
          5: 'Very High'
      };
      return labelMap[level] || `Level ${level}`;
  });

  createChartIfPresent("activity", {
      type: 'bar',
      data: {
          datasets: [{
              label: 'Daily Activity Levels',
              data: popDetails.activity.data,
              backgroundColor: 'rgba(20, 184, 166, 0.7)',
              borderColor: 'rgba(20, 184, 166, 1)',
              borderWidth: 1
          }],
          labels: activityLabels
        },
      options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
              legend: { display: false },
              title: {
                  display: true,
                  text: 'Daily Activity Levels',
                  font: { size: 14, weight: 'bold' }
              }
          },
          scales: {
              y: {
                  beginAtZero: true,
                  ticks: { font: { size: 11 } }
              },
              x: {
                  ticks: { font: { size: 11 } }
              }
          }
      }
  });
  }

  const tableDiv = document.getElementById('table');

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

  if (tableDiv) {
  new gridjs.Grid({
    columns: [
      { id: 'id', hidden: true },
      { id: 'name', name: 'Name', attributes: editableCellAttributes },
      { id: "size", name: 'Agents' },
      { 
        id: 'education', 
        name: 'Education',
        sort: false,
        formatter: (cell) => {
          if (!cell || cell.length === 0) {
            return '';
          }
          const tags = cell.map(item => 
            `<span style="display: inline-block; background-color: #039be5; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; margin: 2px;">${item}</span>`
          ).join(' ');
          return gridjs.html(`<div style="display: flex; flex-wrap: wrap; gap: 4px;">${tags}</div>`);
        }
      },
      { 
        id: 'leanings', 
        name: 'Political Leaning',
        sort: false,
        formatter: (cell) => {
          if (!cell || cell.length === 0) {
            return '';
          }
          const tags = cell.map(item => 
            `<span style="display: inline-block; background-color: #039be5; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; margin: 2px;">${item}</span>`
          ).join(' ');
          return gridjs.html(`<div style="display: flex; flex-wrap: wrap; gap: 4px;">${tags}</div>`);
        }
      },
      { 
        id: 'toxicity', 
        name: 'Toxicity',
        sort: false,
        formatter: (cell) => {
          if (!cell || cell.length === 0) {
            return '';
          }
          const tags = cell.map(item => 
            `<span style="display: inline-block; background-color: #039be5; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; margin: 2px;">${item}</span>`
          ).join(' ');
          return gridjs.html(`<div style="display: flex; flex-wrap: wrap; gap: 4px;">${tags}</div>`);
        }
      },
      { 
        id: 'activity_profiles', 
        name: 'Activity Profiles',
        sort: false,
        formatter: (cell) => {
          if (!cell || cell.length === 0) {
            return '';
          }
          const tags = cell.map(profile => 
            `<span style="display: inline-block; background-color: #039be5; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; margin: 2px;">${profile}</span>`
          ).join(' ');
          return gridjs.html(`<div style="display: flex; flex-wrap: wrap; gap: 4px;">${tags}</div>`);
        }
      },
      {
        id: 'actions',
        name: 'Actions',
        sort: false,
        formatter: (cell, row) => {
          const id = row.cells[0].data;
          return gridjs.html(`
            <div style="display: flex; gap: 8px; justify-content: center;">
              <a href="/admin/population_details/${id}"
                 style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">
                Details
              </a>
               <a href="/admin/delete_population/${id}"
                 style="background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">
                Delete
              </a>
            </div>
          `);
        }
      },
    ],
    server: {
      url: '/admin/populations_data',
      then: results => results.data,
      total: results => results.total,
    },
    search: {
      enabled: true,
      server: {
        url: (prev, search) => {
          return updateUrl(prev, { search });
        },
      },
    },
    sort: {
      enabled: true,
      multiColumn: true,
      server: {
        url: (prev, columns) => {
          const columnIds = ['id', 'name', 'size', 'education', 'leanings', 'toxicity', 'activity_profiles'];
          const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
          return updateUrl(prev, { sort });
        },
      },
    },
    pagination: {
      enabled: true,
      server: {
        url: (prev, page, limit) => {
          return updateUrl(prev, { start: page * limit, length: limit });
        },
      },
    },
  }).render(tableDiv);

  let savedValue;

  // Handle inline edits
  tableDiv.addEventListener('focusin', ev => {
    if (ev.target.tagName === 'TD') {
      savedValue = ev.target.textContent;
    }
  });

  tableDiv.addEventListener('focusout', ev => {
    if (ev.target.tagName === 'TD') {
      if (savedValue !== ev.target.textContent) {
        fetch('/admin/populations_data', {
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

  tableDiv.addEventListener('keydown', ev => {
    if (ev.target.tagName === 'TD') {
      if (ev.key === 'Escape') {
        ev.target.textContent = savedValue;
        ev.target.blur();
      } else if (ev.key === 'Enter') {
        ev.preventDefault();
        ev.target.blur();
      }
    }
  });

  // Handle delete button clicks
  tableDiv.addEventListener('click', function (event) {
    const target = event.target;
    if (target.classList.contains('delete-button')) {
      const id = target.getAttribute('data-id');
      if (confirm('Are you sure you want to delete this population?')) {
        fetch(`/admin/delete_population/${id}`, {
          method: 'DELETE',
        })
        .then(response => {
          if (!response.ok) throw new Error('Failed to delete');
          location.reload(); // Refresh the table
        })
        .catch(err => {
          alert('Error deleting population.');
          console.error(err);
        });
      }
    }
  });
  }

  function displayFileName(input) {
      const display = document.getElementById('file-name-display');
      if (input.files && input.files[0]) {
          display.textContent = '✓ ' + input.files[0].name;
      } else {
          display.textContent = '';
      }
  }

  // Merge populations drag and drop functionality
  let mergeAvailablePopulations = [];
  let mergeSelectedPopulations = [];

  // Load populations from the API
  function loadMergePopulations() {
      fetch('/admin/populations_data')
          .then(response => response.json())
          .then(data => {
              mergeAvailablePopulations = data.data.map(pop => ({
                  id: pop.id,
                  name: pop.name,
                  size: pop.size || 0,
                  username_type: pop.username_type || 'microblogging'
              }));
              renderMergeAvailablePopulations();
          })
          .catch(error => {
              console.error('Error loading populations:', error);
              document.getElementById('merge-available-populations').innerHTML = 
                  '<div class="merge-empty-state">Error loading populations</div>';
          });
  }

  function renderMergeAvailablePopulations() {
      const container = document.getElementById('merge-available-populations');
      const selectedType = document.getElementById('merged_population_type').value;
    
      // Filter out already selected populations
      const available = mergeAvailablePopulations.filter(pop => 
          !mergeSelectedPopulations.find(selected => selected.id === pop.id) &&
          pop.username_type === selectedType
      );

      if (available.length === 0) {
          container.innerHTML = '<div class="merge-empty-state">No populations available</div>';
          return;
      }

      container.innerHTML = available.map(pop => `
          <div class="merge-population-item" 
               draggable="true" 
               data-pop-id="${pop.id}"
               data-pop-name="${pop.name}"
               data-pop-size="${pop.size}"
               data-pop-type="${pop.username_type}">
              <span class="merge-population-name">${pop.name}</span>
              <span class="merge-population-size">${pop.size} agents, ${pop.username_type}</span>
          </div>
      `).join('');

      // Add drag event listeners
      container.querySelectorAll('.merge-population-item').forEach(item => {
          item.addEventListener('dragstart', handleMergeDragStart);
          item.addEventListener('dragend', handleMergeDragEnd);
      });
  }

  function renderMergeSelectedPopulations() {
      const container = document.getElementById('merge-selected-populations');
    
      if (mergeSelectedPopulations.length === 0) {
          container.innerHTML = '<div class="merge-empty-state">Drag populations here</div>';
          return;
      }

      container.innerHTML = mergeSelectedPopulations.map(pop => `
          <div class="merge-population-item">
              <span class="merge-population-name">${pop.name}</span>
              <span class="merge-population-size">${pop.size} agents, ${pop.username_type}</span>
              <button type="button" class="merge-remove-btn" onclick="removeMergePopulation(${pop.id})">×</button>
          </div>
      `).join('');

      // Update hidden field
      document.getElementById('selected_population_ids').value = 
          mergeSelectedPopulations.map(p => p.id).join(',');
  }

  function handleMergeDragStart(e) {
      e.currentTarget.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', JSON.stringify({
          id: e.currentTarget.dataset.popId,
          name: e.currentTarget.dataset.popName,
          size: e.currentTarget.dataset.popSize,
          username_type: e.currentTarget.dataset.popType
      }));
  }

  function handleMergeDragEnd(e) {
      e.currentTarget.classList.remove('dragging');
  }

  function handleMergeDragOver(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      e.currentTarget.classList.add('merge-drag-over');
  }

  function handleMergeDragLeave(e) {
      if (e.currentTarget === e.target) {
          e.currentTarget.classList.remove('merge-drag-over');
      }
  }

  function handleMergeDrop(e) {
      e.preventDefault();
      e.currentTarget.classList.remove('merge-drag-over');
    
      const data = JSON.parse(e.dataTransfer.getData('text/plain'));
    
      // Add to selected if not already there
      const parsedId = parseInt(data.id, 10);
      if (!mergeSelectedPopulations.find(p => p.id === parsedId)) {
          mergeSelectedPopulations.push({
              id: parsedId,
              name: data.name,
              size: parseInt(data.size, 10) || 0,
              username_type: data.username_type || document.getElementById('merged_population_type').value
          });
          renderMergeSelectedPopulations();
          renderMergeAvailablePopulations();
      }
  }

  function removeMergePopulation(popId) {
      mergeSelectedPopulations = mergeSelectedPopulations.filter(p => p.id !== popId);
      renderMergeSelectedPopulations();
      renderMergeAvailablePopulations();
  }

  // Initialize merge drag and drop
  document.addEventListener('DOMContentLoaded', function() {
      loadMergePopulations();
      bindById('merged_population_type', 'change', function() {
          mergeSelectedPopulations = [];
          renderMergeSelectedPopulations();
          renderMergeAvailablePopulations();
      });
    
      const selectedContainer = document.getElementById('merge-selected-populations');
      if (!selectedContainer) return;
      selectedContainer.addEventListener('dragover', handleMergeDragOver);
      selectedContainer.addEventListener('drop', handleMergeDrop);
      selectedContainer.addEventListener('dragleave', handleMergeDragLeave);
  });

  // Form validation
  bindById('merge_populations_form', 'submit', function(e) {
      if (mergeSelectedPopulations.length < 2) {
          e.preventDefault();
          alert('Please select at least 2 populations to merge');
          return false;
      }
  });

  // Profession backgrounds selection (all active by default)
  let selectedProfessionBackgrounds = new Set(
      YS_DATA_POPULATIONS.professionBackgrounds
  );

  function toggleProfessionBackgrounds() {
      const section = document.getElementById('profession-backgrounds-section');
      const toggle = document.getElementById('profession-backgrounds-toggle');
      section.classList.toggle('expanded');
      toggle.textContent = section.classList.contains('expanded') ? '▼' : '▶';
  }

  function toggleProfessionTag(tagElement) {
      const background = tagElement.dataset.background;
    
      if (selectedProfessionBackgrounds.has(background)) {
          selectedProfessionBackgrounds.delete(background);
          tagElement.classList.add('inactive');
      } else {
          selectedProfessionBackgrounds.add(background);
          tagElement.classList.remove('inactive');
      }
    
      // Update validation state
      updateProfessionValidation();
  }

  function updateProfessionValidation() {
      // Provide visual feedback if no categories selected
      const container = document.getElementById('profession-tags-container');
      if (selectedProfessionBackgrounds.size === 0) {
          container.style.borderColor = '#fcc';
      } else {
          container.style.borderColor = '#e5e7eb';
      }
  }

  // Add hidden inputs for profession backgrounds before form submission
  document.addEventListener('DOMContentLoaded', function() {
      const form = document.getElementById('popcreate_form');
      form.addEventListener('submit', function(e) {
          // Validate that at least one profession category is selected
          if (selectedProfessionBackgrounds.size === 0) {
              e.preventDefault();
              alert('Please select at least one Profession Category. This field is required.');
              return false;
          }
        
          // Remove old hidden inputs for profession backgrounds
          const oldInputs = form.querySelectorAll('input[name="profession_backgrounds"]');
          oldInputs.forEach(input => input.remove());
        
          // Add new hidden inputs for selected profession backgrounds
          selectedProfessionBackgrounds.forEach(background => {
              const input = document.createElement('input');
              input.type = 'hidden';
              input.name = 'profession_backgrounds';
              input.value = background;
              form.appendChild(input);
          });
      }, true); // Use capture phase to run before other handlers
  });

  // Multi-select functionality with percentages
  const multiSelectData = {
      education_levels: {},  // Changed to object: {id: {label, percentage}}
      political_leanings: {},
      toxicity_levels: {},
      age_classes: {}
  };

  function updateFemalePercentage() {
      const malePercentage = parseInt(document.getElementById('male_percentage').value) || 0;
      const femalePercentage = 100 - malePercentage;
      if (femalePercentage >= 0 && femalePercentage <= 100) {
          document.getElementById('female_percentage').value = femalePercentage;
          document.getElementById('gender_validation').style.display = 'none';
      } else {
          document.getElementById('gender_validation').style.display = 'inline';
          document.getElementById('gender_validation').style.color = '#e74c3c';
      }
  }

  function updateMalePercentage() {
      const femalePercentage = parseInt(document.getElementById('female_percentage').value) || 0;
      const malePercentage = 100 - femalePercentage;
      if (malePercentage >= 0 && malePercentage <= 100) {
          document.getElementById('male_percentage').value = malePercentage;
          document.getElementById('gender_validation').style.display = 'none';
      } else {
          document.getElementById('gender_validation').style.display = 'inline';
          document.getElementById('gender_validation').style.color = '#e74c3c';
      }
  }

  function toggleDropdown(fieldName) {
      const dropdown = document.getElementById(fieldName + '_dropdown');
      dropdown.classList.toggle('active');
    
      // Close other dropdowns
      document.querySelectorAll('.multi-select-dropdown').forEach(dd => {
          if (dd.id !== fieldName + '_dropdown') {
              dd.classList.remove('active');
          }
      });
  }

  function toggleOption(fieldName, label, id) {
      const data = multiSelectData[fieldName];
    
      if (data[id]) {
          delete data[id];
      } else {
          data[id] = {label: label, percentage: 0};
      }
    
      updateDisplay(fieldName);
      updateOptionStyles(fieldName);
      updatePercentages(fieldName);
  }

  function removeTag(fieldName, id) {
      const data = multiSelectData[fieldName];
      if (data[id]) {
          delete data[id];
      }
      updateDisplay(fieldName);
      updateOptionStyles(fieldName);
      updatePercentages(fieldName);
  }

  function updateDisplay(fieldName) {
      const display = document.getElementById(fieldName + '_display');
      const data = multiSelectData[fieldName];
      const items = Object.entries(data);
    
      if (items.length === 0) {
          display.innerHTML = '<span class="multi-select-placeholder">Click to select...</span>';
      } else {
          display.innerHTML = items.map(([id, item]) => 
              `<span class="multi-select-tag">
                  ${item.label}
                  <span class="multi-select-tag-remove" onclick="event.stopPropagation(); removeTag('${fieldName}', '${id}')">×</span>
              </span>`
          ).join('');
      }
    
      // Trigger validation check when display updates
      if (typeof validateFormFields === 'function') {
          validateFormFields();
      }
  }

  function updateOptionStyles(fieldName) {
      const dropdown = document.getElementById(fieldName + '_dropdown');
      const data = multiSelectData[fieldName];
    
      dropdown.querySelectorAll('.multi-select-option').forEach(option => {
          const label = option.textContent.trim();
          const isSelected = Object.values(data).some(item => item.label === label);
          if (isSelected) {
              option.classList.add('selected');
          } else {
              option.classList.remove('selected');
          }
      });
  }

  function updatePercentages(fieldName) {
      const data = multiSelectData[fieldName];
      const items = Object.entries(data);
      const container = document.getElementById(fieldName + '_percentages');
      const containerRow = document.getElementById(fieldName + '_percentages_container');
    
      if (items.length === 0) {
          containerRow.style.display = 'none';
          return;
      }
    
      containerRow.style.display = '';
    
      // Check if all percentages are 0 (uninitialized)
      const allZero = items.every(([id, item]) => {
          const value = item.percentage;
          return value === 0 || value === undefined || value === null || value === '';
      });
    
      // Only split evenly if all percentages are 0 (uninitialized)
      // This preserves hardcoded defaults for age_classes while maintaining
      // the even split behavior for other fields
      if (allZero) {
          const evenSplit = parseFloat((100 / items.length).toFixed(2));
          items.forEach(([id, item]) => {
              item.percentage = evenSplit;
          });
      }
    
      // Render percentage inputs
      container.innerHTML = items.map(([id, item]) => `
          <div style="display: flex; align-items: center; gap: 8px; padding: 6px; background: #f9f9f9; border-radius: 4px;">
              <span style="flex: 1; font-size: 0.9em; font-weight: 500;">${item.label}</span>
              <input type="number" 
                     class="percentage-input-compact" 
                     min="0" 
                     max="100" 
                     step="0.01"
                     value="${item.percentage}"
                     onchange="updatePercentageValue('${fieldName}', '${id}', this.value)"
                     style="width: 80px; padding: 6px; border: 1px solid #ddd; border-radius: 3px; text-align: center;">
              <span style="font-size: 0.85em; color: #666;">%</span>
          </div>
      `).join('');
    
      validatePercentageTotal(fieldName);
  }

  function updatePercentageValue(fieldName, id, value) {
      const data = multiSelectData[fieldName];
      if (data[id]) {
          data[id].percentage = parseFloat(value) || 0;
      }
      validatePercentageTotal(fieldName);
  }

  function validatePercentageTotal(fieldName) {
      const data = multiSelectData[fieldName];
      const items = Object.values(data);
      const validation = document.getElementById(fieldName + '_validation');
    
      if (items.length === 0) {
          validation.style.display = 'none';
          return;
      }
    
      const total = items.reduce((sum, item) => sum + item.percentage, 0);
      validation.style.display = 'block';
    
      if (Math.abs(total - 100) < 0.01) {
          validation.className = 'percentage-validation-compact success';
          validation.textContent = `✓ Total: ${total.toFixed(2)}%`;
      } else {
          validation.className = 'percentage-validation-compact error';
          validation.textContent = `⚠ Total: ${total.toFixed(2)}% (must equal 100%)`;
      }
  }

  // Close dropdowns when clicking outside
  document.addEventListener('click', function(e) {
      if (!e.target.closest('.multi-select-wrapper')) {
          document.querySelectorAll('.multi-select-dropdown').forEach(dd => {
              dd.classList.remove('active');
          });
      }
  });

  // Add hidden inputs before form submission
  bindById('popcreate_form', 'submit', function(e) {
      // Validate gender percentages
      const malePercentage = parseInt(document.getElementById('male_percentage').value) || 0;
      const femalePercentage = parseInt(document.getElementById('female_percentage').value) || 0;
      if (malePercentage + femalePercentage !== 100) {
          e.preventDefault();
          alert('Gender distribution must total 100%');
          return false;
      }
    
      // Validate that age_classes is selected (mandatory field)
      const ageClassesData = multiSelectData['age_classes'];
      const ageClassesItems = Object.values(ageClassesData);
      if (ageClassesItems.length === 0) {
          e.preventDefault();
          alert('Please select at least one Age Class. This field is required.');
          return false;
      }
    
      // Validate percentages before submission
      const fieldsToValidate = ['education_levels', 'political_leanings', 'toxicity_levels', 'age_classes'];
      for (const fieldName of fieldsToValidate) {
          const data = multiSelectData[fieldName];
          const items = Object.values(data);
          if (items.length > 0) {
              const total = items.reduce((sum, item) => sum + item.percentage, 0);
              if (Math.abs(total - 100) > 0.01) {
                  e.preventDefault();
                  alert(`Please ensure ${fieldName.replace(/_/g, ' ')} percentages sum to 100%`);
                  return false;
              }
          }
      }
    
      // Validate activity profiles percentages
      if (assignedProfiles.length > 0 && !validatePercentages()) {
          e.preventDefault();
          alert('Please ensure that the total percentage of assigned activity profiles equals 100%');
          return false;
      }
    
      // Remove old hidden inputs
      this.querySelectorAll('input[name="education_levels"], input[name="political_leanings"], input[name="toxicity_levels"], input[name="age_classes"]').forEach(input => input.remove());
      this.querySelectorAll('input[name="education_levels_percentages"], input[name="political_leanings_percentages"], input[name="toxicity_levels_percentages"], input[name="age_classes_percentages"]').forEach(input => input.remove());
    
      // Add new hidden inputs for multi-select values (IDs for backward compatibility)
      Object.keys(multiSelectData).forEach(fieldName => {
          const data = multiSelectData[fieldName];
          Object.entries(data).forEach(([id, item]) => {
              const input = document.createElement('input');
              input.type = 'hidden';
              input.name = fieldName;
              input.value = id;
              this.appendChild(input);
          });
      });
    
      // Add hidden inputs for percentages (JSON format for easy parsing)
      Object.keys(multiSelectData).forEach(fieldName => {
          const data = multiSelectData[fieldName];
          const percentageData = {};
          Object.entries(data).forEach(([id, item]) => {
              percentageData[id] = item.percentage;
          });
        
          const input = document.createElement('input');
          input.type = 'hidden';
          input.name = fieldName + '_percentages';
          input.value = JSON.stringify(percentageData);
          this.appendChild(input);
      });
  });

  // Initialize age classes with default values
  document.addEventListener('DOMContentLoaded', function() {
      // Hardcoded default percentages for age classes
      const defaultPercentages = {
          'Youth': 35,
          'Adults': 42,
          'Middle-aged': 18,
          'Elderly': 5
      };
    
      const ageClassDefaults = YS_DATA_POPULATIONS.ageClasses;
    
      // Set default age classes with explicit percentages so form submission
      // serializes a usable age distribution even before any user edit.
      multiSelectData.age_classes = Object.fromEntries(
          Object.entries(ageClassDefaults).map(([id, item]) => [
              id,
              {
                  label: item.label,
                  percentage: defaultPercentages[item.name] ?? 0
              }
          ])
      );
      updateDisplay('age_classes');
      updateOptionStyles('age_classes');
      updatePercentages('age_classes');
  });

  // Toggle activity profiles section
  function toggleActivityProfiles() {
      const section = document.getElementById('activity-profiles-section');
      const toggle = document.getElementById('activity-profiles-toggle');
      section.classList.toggle('expanded');
      toggle.textContent = section.classList.contains('expanded') ? '▲' : '▼';
  }

  // Drag and drop functionality for activity profiles
  let assignedProfiles = [];

  function initDragAndDrop() {
      const availableContainer = document.getElementById('available-profiles');
      const assignedContainer = document.getElementById('assigned-profiles');

      // Make profile items draggable
      document.querySelectorAll('.profile-item-compact').forEach(item => {
          item.addEventListener('dragstart', handleDragStart);
          item.addEventListener('dragend', handleDragEnd);
      });

      // Make assigned profiles area droppable
      assignedContainer.addEventListener('dragover', handleDragOver);
      assignedContainer.addEventListener('drop', handleDrop);
      assignedContainer.addEventListener('dragleave', handleDragLeave);
  }

  function handleDragStart(e) {
      e.currentTarget.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'copy';
      e.dataTransfer.setData('text/plain', JSON.stringify({
          id: e.currentTarget.dataset.profileId,
          name: e.currentTarget.dataset.profileName,
          hours: e.currentTarget.dataset.profileHours
      }));
  }

  function handleDragEnd(e) {
      e.currentTarget.classList.remove('dragging');
  }

  function handleDragOver(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      e.currentTarget.classList.add('drag-over-compact');
  }

  function handleDragLeave(e) {
      if (e.currentTarget === e.target) {
          e.currentTarget.classList.remove('drag-over-compact');
      }
  }

  function handleDrop(e) {
      e.preventDefault();
      e.currentTarget.classList.remove('drag-over-compact');
    
      const data = JSON.parse(e.dataTransfer.getData('text/plain'));
    
      // Check if profile is already assigned
      if (assignedProfiles.find(p => p.id === data.id)) {
          return; // Already assigned
      }

      // Add to assigned profiles
      assignedProfiles.push({
          id: data.id,
          name: data.name,
          hours: data.hours,
          percentage: 0
      });

      renderAssignedProfiles();
      validatePercentages();
  }

  function renderAssignedProfiles() {
      const container = document.getElementById('assigned-profiles');
    
      if (assignedProfiles.length === 0) {
          container.innerHTML = '<div class="empty-state-compact">Drag profiles here to assign them</div>';
          return;
      }

      container.innerHTML = '<div class="assigned-profiles-grid">' + assignedProfiles.map(profile => `
          <div class="assigned-profile-compact">
              <span class="assigned-profile-name-compact">${profile.name}</span>
              <input type="number" 
                     class="percentage-input-compact" 
                     min="0" 
                     max="100" 
                     step="0.01"
                     placeholder="%" 
                     value="${profile.percentage || ''}"
                     onchange="updatePercentage('${profile.id}', this.value)">
              <span style="font-size: 0.75em; color: #666;">%</span>
              <button type="button" class="remove-profile-btn-compact" onclick="removeProfile('${profile.id}')">×</button>
          </div>
      `).join('') + '</div>';
  }

  function updatePercentage(profileId, percentage) {
      const profile = assignedProfiles.find(p => p.id === profileId);
      if (profile) {
          profile.percentage = parseFloat(percentage) || 0;
          validatePercentages();
          updateHiddenField();
      }
  }

  function removeProfile(profileId) {
      assignedProfiles = assignedProfiles.filter(p => p.id !== profileId);
      renderAssignedProfiles();
      validatePercentages();
      updateHiddenField();
  }

  function validatePercentages() {
      const validation = document.getElementById('percentage-validation');
      const total = assignedProfiles.reduce((sum, p) => sum + (p.percentage || 0), 0);
    
      if (assignedProfiles.length === 0) {
          validation.style.display = 'none';
          return true;
      }

      validation.style.display = 'block';
    
      if (Math.abs(total - 100) < 0.01) {
          validation.className = 'percentage-validation-compact success';
          validation.textContent = `✓ Total: ${total.toFixed(2)}% - Perfect!`;
          return true;
      } else {
          validation.className = 'percentage-validation-compact error';
          validation.textContent = `⚠ Total: ${total.toFixed(2)}% - Must equal 100%`;
          return false;
      }
  }

  function updateHiddenField() {
      const data = assignedProfiles.map(p => ({
          id: p.id,
          name: p.name,
          percentage: p.percentage || 0
      }));
      document.getElementById('activity_profiles_data').value = JSON.stringify(data);
  }

  // Initialize on page load
  document.addEventListener('DOMContentLoaded', function() {
      initDragAndDrop();
    
      // Set "Always On" as default with 100%
      if (window.YS_DATA_POPULATIONS && YS_DATA_POPULATIONS.alwaysOnProfile) {
                  assignedProfiles.push({
                      id: YS_DATA_POPULATIONS.alwaysOnProfile.id,
                      name: YS_DATA_POPULATIONS.alwaysOnProfile.name,
                      hours: YS_DATA_POPULATIONS.alwaysOnProfile.hours,
                      percentage: 100
                  });
                  renderAssignedProfiles();
                  validatePercentages();
                  updateHiddenField();
              }
        
    
  });

  // Function to show/hide distribution-specific parameters
  function updateDistributionParams() {
      const distribution = document.getElementById('actions_distribution').value;
    
      // Hide all parameter sections and disable their inputs
      const poissonParams = document.getElementById('poisson-params');
      const geometricParams = document.getElementById('geometric-params');
      const zipfParams = document.getElementById('zipf-params');
    
      poissonParams.style.display = 'none';
      geometricParams.style.display = 'none';
      zipfParams.style.display = 'none';
    
      document.getElementById('poisson_lambda').disabled = true;
      document.getElementById('geometric_p').disabled = true;
      document.getElementById('zipf_s').disabled = true;
    
      // Show the relevant parameter section and enable its input
      switch(distribution) {
          case 'Poisson':
              poissonParams.style.display = 'block';
              document.getElementById('poisson_lambda').disabled = false;
              break;
          case 'Geometric':
              geometricParams.style.display = 'block';
              document.getElementById('geometric_p').disabled = false;
              break;
          case 'Zipf':
              zipfParams.style.display = 'block';
              document.getElementById('zipf_s').disabled = false;
              break;
          // Uniform doesn't need extra parameters
      }
  }

  // Form validation to enable/disable submit button
  function validateFormFields() {
      const popName = document.getElementById('pop_name').value.trim();
      const nAgents = document.getElementById('n_agents').value;
      const hasAgeClasses = Object.keys(multiSelectData.age_classes).length > 0;
      const hasEducation = Object.keys(multiSelectData.education_levels).length > 0;
      const hasPolitical = Object.keys(multiSelectData.political_leanings).length > 0;
      const hasToxicity = Object.keys(multiSelectData.toxicity_levels).length > 0;
    
      const submitBtn = document.getElementById('create_population_btn');
      const isValid = popName && nAgents && hasAgeClasses && hasEducation && hasPolitical && hasToxicity;
    
      submitBtn.disabled = !isValid;
    
      // Visual feedback for required fields
      if (!hasAgeClasses) {
          document.getElementById('age_classes_display_wrapper').style.borderColor = '#fcc';
      } else {
          document.getElementById('age_classes_display_wrapper').style.borderColor = '#ddd';
      }

      if (!hasEducation) {
          document.getElementById('education_levels_display_wrapper').style.borderColor = '#fcc';
      } else {
          document.getElementById('education_levels_display_wrapper').style.borderColor = '#ddd';
      }
    
      if (!hasPolitical) {
          document.getElementById('political_leanings_display_wrapper').style.borderColor = '#fcc';
      } else {
          document.getElementById('political_leanings_display_wrapper').style.borderColor = '#ddd';
      }
    
      if (!hasToxicity) {
          document.getElementById('toxicity_levels_display_wrapper').style.borderColor = '#fcc';
      } else {
          document.getElementById('toxicity_levels_display_wrapper').style.borderColor = '#ddd';
      }
    
      return isValid;
  }

  // Add event listeners to all fields that affect validation
  document.addEventListener('DOMContentLoaded', function() {
  bindById('pop_name', 'input', validateFormFields);
  bindById('n_agents', 'input', validateFormFields);
    
      // Initial validation
      validateFormFields();
  });

  Object.assign(window, {
      displayFileName,
      toggleActivityProfiles,
      toggleProfessionBackgrounds,
      toggleProfessionTag,
      updateFemalePercentage,
      updateMalePercentage,
      toggleDropdown,
      toggleOption,
      updateDistributionParams
  });
})();
