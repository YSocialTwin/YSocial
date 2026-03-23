/**
 * AdminClients - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminClients = (function() {
  // Sync display input with hidden input
  document.getElementById('days_display').addEventListener('change', function() {
      document.getElementById('days_input').value = this.value;
  });
  document.getElementById('days_display').addEventListener('input', function() {
      document.getElementById('days_input').value = this.value;
  });

  // Toggle between finite and infinite duration
  document.getElementById('infinite_duration').addEventListener('change', function() {
      const daysDisplay = document.getElementById('days_display');
      const daysInput = document.getElementById('days_input');
      const defaultDays = '30';
      if (this.checked) {
          // Store current value before switching to infinite
          daysDisplay.dataset.previousValue = daysDisplay.value;
          daysDisplay.value = '∞';
          daysDisplay.disabled = true;
          daysDisplay.style.opacity = '0.5';
          daysInput.value = -1;
      } else {
          // Restore previous value or use default
          daysDisplay.value = daysDisplay.dataset.previousValue || defaultDays;
          daysDisplay.disabled = false;
          daysDisplay.style.opacity = '1';
          daysInput.value = daysDisplay.value;
      }
  });

  // Toggle follow decay parameters visibility
  document.getElementById('follow_decay_enabled').addEventListener('change', function() {
      const paramsDiv = document.getElementById('follow_decay_params');
      if (this.checked) {
          paramsDiv.style.display = 'block';
      } else {
          paramsDiv.style.display = 'none';
      }
  });

  // Toggle simulation advanced parameters visibility
  function toggleSimulationAdvancedParams() {
      const checkbox = document.getElementById('show_simulation_advanced_params');
      const fields = document.getElementById('simulation_advanced_params_fields');
    
      if (checkbox && fields) {
          fields.style.display = checkbox.checked ? 'block' : 'none';
      }
  }

  // Initialize on page load
  document.addEventListener('DOMContentLoaded', function() {
      toggleSimulationAdvancedParams();
  });

  function toggleLLMFields() {
      const backendElement = document.getElementById('llm_backend');
      const vllmFields = document.getElementById('vllm_fields');
      const ollamaFields = document.getElementById('ollama_fields');
      const imageTranscriptionCheckbox = document.getElementById('enable_image_transcription');
    
      if (!backendElement) return;
      const backend = backendElement.value;
    
      if (backend === 'vllm') {
          vllmFields.style.display = 'block';
          ollamaFields.style.display = 'none';
          // vLLM doesn't need model fetching, enable submit button
          updateFormButtonStateForBackend('vllm');
        
          // Enable "Share and comment an Image" only if Image Transcription is enabled
          if (imageTranscriptionCheckbox && imageTranscriptionCheckbox.checked) {
              enableImageAction();
          } else {
              disableImageAction();
          }
      } else {
          vllmFields.style.display = 'none';
          ollamaFields.style.display = 'block';
          // Ollama requires model fetching
          updateFormButtonStateForBackend('ollama');
          // When not vLLM, disable Image action (since Ollama handles it differently)
          disableImageAction();
      }
  }

  function toggleAdvancedSettings() {
      const checkbox = document.getElementById('show_advanced_settings');
      const fields = document.getElementById('advanced_settings_fields');
    
      if (checkbox.checked) {
          fields.style.display = 'block';
      } else {
          fields.style.display = 'none';
      }
  }

  function toggleImageTranscription() {
      const checkbox = document.getElementById('enable_image_transcription');
      const fields = document.getElementById('image_transcription_fields');
      const backendElement = document.getElementById('llm_backend');
    
      if (!checkbox || !fields) return;
    
      const inputs = fields.querySelectorAll('input');
      const backend = backendElement ? backendElement.value : null;
    
      if (checkbox.checked) {
          fields.style.display = 'block';
          // Enable the input fields when checked
          inputs.forEach(input => {
              input.disabled = false;
          });
        
          // Enable "Share and comment an Image" action when vLLM is selected and Image Transcription is enabled
          if (backend === 'vllm') {
              enableImageAction();
          }
      } else {
          fields.style.display = 'none';
          // Disable the input fields when unchecked so they don't get submitted
          inputs.forEach(input => {
              input.disabled = true;
          });
        
          // Disable "Share and comment an Image" action when Image Transcription is disabled
          disableImageAction();
      }
  }

  // Initialize on page load
  document.addEventListener('DOMContentLoaded', function() {
      toggleLLMFields();
      toggleAdvancedSettings();
      toggleImageTranscription();
  });

  // Initialize chart with default data
  function initActivityChart() {
      const defaultData = [
          0.023, 0.021, 0.020, 0.020, 0.018, 0.017, 0.017, 0.018,
          0.020, 0.020, 0.021, 0.022, 0.024, 0.027, 0.030, 0.032,
          0.032, 0.032, 0.032, 0.031, 0.030, 0.029, 0.027, 0.025
      ];
      const labels = Array.from({length: 24}, (_, i) => i.toString());
    
      // Convert to percentages
      const activityData = defaultData.map(v => v * 100);
      const maxValue = Math.max(...activityData);
      const yAxisMax = Math.ceil(maxValue * 1.1);

      const ctx = document.getElementById('activity_rates_create');
      if (!ctx) return;

      new Chart(ctx, {
          type: 'bar',
          data: {
              labels: labels,
              datasets: [{
                  label: 'Activity %',
                  data: activityData,
                  backgroundColor: 'rgba(34, 197, 94, 0.6)',
                  borderColor: 'rgba(34, 197, 94, 1)',
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
                              return 'Active: ' + context.parsed.y.toFixed(2) + '%';
                          }
                      }
                  }
              },
              scales: {
                  y: {
                      beginAtZero: true,
                      suggestedMax: yAxisMax,
                      ticks: {
                          font: { size: 10 },
                          callback: function(value) {
                              return value + '%';
                          }
                      },
                      grid: {
                          color: 'rgba(0, 0, 0, 0.05)'
                      }
                  },
                  x: {
                      ticks: {
                          font: { size: 9 }
                      },
                      grid: {
                          display: false
                      }
                  }
              }
          }
      });
  }

  // Initialize chart when details are expanded
  document.addEventListener('DOMContentLoaded', function() {
      const detailsElements = document.querySelectorAll('details');
      detailsElements.forEach(details => {
          details.addEventListener('toggle', function() {
              if (this.open && this.querySelector('#activity_rates_create')) {
                  setTimeout(initActivityChart, 100);
              }
          });
      });
  });

                                              document.querySelectorAll('.number-scale').forEach(scale => {
                                                const boxes = scale.querySelectorAll('.number-box');
                                                const wrapper = scale.closest('.scale-wrapper');
                                                const hiddenInput = wrapper.querySelector('input[type="hidden"]');

                                                boxes.forEach(box => {
                                                  box.addEventListener('click', () => {
                                                    boxes.forEach(b => b.classList.remove('selected'));
                                                    box.classList.add('selected');
                                                    hiddenInput.value = box.dataset.value;
                                                    display.textContent = box.dataset.value;
                                                  });
                                                });
                                              });

  // Track if models have been fetched and validated
  let llmModelsFetched = false;
  let llmModelSelected = false;

  // Enable disabled inputs before form submission so their values are included

  // Check if form should be enabled based on backend selection
  function updateFormButtonStateForBackend(backend) {
      const submitButton = document.getElementById('create_client_button');
      if (submitButton) {
          if (backend === 'vllm') {
              // vLLM doesn't require model fetching, enable button immediately
              submitButton.disabled = false;
          } else {
              // Ollama requires model fetching and selection
              if (YS_DATA_CLIENTS.llmAgentsEnabled) {
              submitButton.disabled = !(llmModelsFetched && llmModelSelected);
              } else {
              submitButton.disabled = false;
              }
          }
      }
  }

  // Check if form should be enabled (for Ollama mode)
  function updateFormButtonState() {
      const submitButton = document.getElementById('create_client_button');
      if (submitButton) {
          const backend = document.getElementById('llm_backend')?.value || 'ollama';
          if (backend === 'vllm') {
              // vLLM mode - always enabled
              submitButton.disabled = false;
          } else {
              // Ollama mode - check if models fetched
              if (YS_DATA_CLIENTS.llmAgentsEnabled) {
              submitButton.disabled = !(llmModelsFetched && llmModelSelected);
              } else {
              submitButton.disabled = false;
              }
          }
      }
  }

  // Fetch models for client LLM configuration
  function fetchModelsForClient() {
      const urlInput = document.getElementById('custom_llm_url_client');
      const select = document.getElementById('models_select_client');
      const status = document.getElementById('llm_url_status_client');
      const llmUrl = urlInput.value.trim();
    
      if (!llmUrl) {
          alert('Please enter an LLM server URL');
          return;
      }
    
      status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Fetching...';
    
      fetch(`/admin/api/fetch_models?llm_url=${encodeURIComponent(llmUrl)}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                  llmModelsFetched = false;
                  updateFormButtonState();
                  setTimeout(() => { status.innerHTML = ''; }, 5000);
              } else {
                  select.innerHTML = '<option value="">Select a model</option>';
                  data.models.forEach(model => {
                      const option = document.createElement('option');
                      option.value = model;
                      option.textContent = model;
                      select.appendChild(option);
                  });
                  status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> ' + data.models.length + ' models loaded</span>';
                  llmModelsFetched = true;
                  // Reset model selection since we just loaded new models
                  llmModelSelected = false;
                  updateFormButtonState();
                  setTimeout(() => { status.innerHTML = ''; }, 3000);
              }
          })
          .catch(error => {
              status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
              llmModelsFetched = false;
              updateFormButtonState();
              setTimeout(() => { status.innerHTML = ''; }, 5000);
          });
  }

  // Validate that minicpm-v:latest is available for image transcription
  function validateImageLLMModel() {
      const llmVUrlInput = document.getElementById('custom_llm_url_v_client');
      const status = document.getElementById('llm_v_url_status_client');
      const validationStatus = document.getElementById('llm_v_validation_status');
      const llmVUrl = llmVUrlInput.value.trim();
      const modelName = 'minicpm-v:latest';
    
      if (!llmVUrl) {
          alert('Please enter an LLM server URL for image transcription');
          return;
      }
    
      status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Validating...';
    
      fetch(`/admin/api/fetch_models?llm_url=${encodeURIComponent(llmVUrl)}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                  validationStatus.value = 'false';
                  disableImageAction();
                  alert('Unable to connect to the LLM server. Image sharing/commenting functionality will remain disabled.');
                  setTimeout(() => { status.innerHTML = ''; }, 5000);
              } else {
                  // Check if minicpm-v:latest model exists in fetched models
                  const modelExists = data.models.includes(modelName);
                
                  if (modelExists) {
                      status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> Model "' + modelName + '" found and validated!</span>';
                      validationStatus.value = 'true';
                      enableImageAction();
                      setTimeout(() => { status.innerHTML = ''; }, 3000);
                  } else {
                      status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Model "' + modelName + '" not found on this server!</span>';
                      validationStatus.value = 'false';
                      disableImageAction();
                      alert('The minicpm-v:latest model is not available on the specified server. Image sharing/commenting functionality will remain disabled.');
                  }
              }
          })
          .catch(error => {
              status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
              validationStatus.value = 'false';
              disableImageAction();
              alert('Failed to connect to the LLM server. Image sharing/commenting functionality will remain disabled.');
              setTimeout(() => { status.innerHTML = ''; }, 5000);
          });
  }

  // Disable the "Share and comment an Image" action
  function disableImageAction() {
      const imageScale = document.getElementById('image');
      const imageScaleWrapper = imageScale ? imageScale.closest('.scale-wrapper') : null;
      const warning = document.getElementById('image_action_warning');
    
      if (imageScaleWrapper) {
          const numberBoxes = imageScaleWrapper.querySelectorAll('.number-box');
          numberBoxes.forEach(box => {
              if (box.dataset.value !== '0') {
                  box.style.opacity = '0.3';
                  box.style.pointerEvents = 'none';
                  box.style.cursor = 'not-allowed';
              }
          });
        
          // Force selection to 0
          numberBoxes.forEach(box => box.classList.remove('selected'));
          numberBoxes[0].classList.add('selected');
          imageScale.value = '0';
      }
    
      if (warning) {
          warning.style.display = 'block';
      }
  }

  // Enable the "Share and comment an Image" action
  function enableImageAction() {
      const imageScale = document.getElementById('image');
      const imageScaleWrapper = imageScale ? imageScale.closest('.scale-wrapper') : null;
      const warning = document.getElementById('image_action_warning');
    
      if (imageScaleWrapper) {
          const numberBoxes = imageScaleWrapper.querySelectorAll('.number-box');
          numberBoxes.forEach(box => {
              box.style.opacity = '1';
              box.style.pointerEvents = 'auto';
              box.style.cursor = 'pointer';
          });
      }
    
      if (warning) {
          warning.style.display = 'none';
      }
  }

  // Handle mutual exclusivity between synthetic network and file upload
  function updateNetworkInputStates() {
      const networkModelSelect = document.getElementById('network_model_select');
      const networkFileInput = document.getElementById('network_file_create');
      const networkFileLabel = document.querySelector('.file-upload-label-network-create');
      const erParamField = document.getElementById('er_param_field');
      const baParamField = document.getElementById('ba_param_field');
      const wsParamField = document.getElementById('ws_param_field');
      const wsParamField2 = document.getElementById('ws_param_field2');
      const plcParamField = document.getElementById('plc_param_field');
      const plcParamField2 = document.getElementById('plc_param_field2');
      const sbmParamField = document.getElementById('sbm_param_field');
      const sbmParamField2 = document.getElementById('sbm_param_field2');
      const sbmParamField3 = document.getElementById('sbm_param_field3');
      const lfrParamField = document.getElementById('lfr_param_field');
      const lfrParamField2 = document.getElementById('lfr_param_field2');
      const lfrParamField3 = document.getElementById('lfr_param_field3');
      const lfrParamField4 = document.getElementById('lfr_param_field4');
    
      if (!networkModelSelect || !networkFileInput) return;
    
      const modelSelected = networkModelSelect.value !== '';
      const fileSelected = networkFileInput.files && networkFileInput.files.length > 0;
    
      // If synthetic model is selected, disable file upload
      if (modelSelected) {
          networkFileInput.disabled = true;
          if (networkFileLabel) {
              networkFileLabel.classList.add('disabled');
          }
      } else {
          networkFileInput.disabled = false;
          if (networkFileLabel) {
              networkFileLabel.classList.remove('disabled');
          }
      }
    
      // If file is uploaded, disable synthetic model selection
      if (fileSelected) {
          networkModelSelect.disabled = true;
      } else {
          networkModelSelect.disabled = false;
      }
    
      // Show/hide parameter fields based on model selection
      if (erParamField) erParamField.style.display = 'none';
      if (baParamField) baParamField.style.display = 'none';
      if (wsParamField) wsParamField.style.display = 'none';
      if (wsParamField2) wsParamField2.style.display = 'none';
      if (plcParamField) plcParamField.style.display = 'none';
      if (plcParamField2) plcParamField2.style.display = 'none';
      if (sbmParamField) sbmParamField.style.display = 'none';
      if (sbmParamField2) sbmParamField2.style.display = 'none';
      if (sbmParamField3) sbmParamField3.style.display = 'none';
      if (lfrParamField) lfrParamField.style.display = 'none';
      if (lfrParamField2) lfrParamField2.style.display = 'none';
      if (lfrParamField3) lfrParamField3.style.display = 'none';
      if (lfrParamField4) lfrParamField4.style.display = 'none';
    
      if (networkModelSelect.value === 'ER' && erParamField) {
          erParamField.style.display = 'block';
      } else if (networkModelSelect.value === 'BA' && baParamField) {
          baParamField.style.display = 'block';
      } else if (networkModelSelect.value === 'WS') {
          if (wsParamField) wsParamField.style.display = 'block';
          if (wsParamField2) wsParamField2.style.display = 'block';
      } else if (networkModelSelect.value === 'PLC') {
          if (plcParamField) plcParamField.style.display = 'block';
          if (plcParamField2) plcParamField2.style.display = 'block';
      } else if (networkModelSelect.value === 'SBM') {
          if (sbmParamField) sbmParamField.style.display = 'block';
          if (sbmParamField2) sbmParamField2.style.display = 'block';
          if (sbmParamField3) sbmParamField3.style.display = 'block';
      } else if (networkModelSelect.value === 'LFR') {
          if (lfrParamField) lfrParamField.style.display = 'block';
          if (lfrParamField2) lfrParamField2.style.display = 'block';
          if (lfrParamField3) lfrParamField3.style.display = 'block';
          if (lfrParamField4) lfrParamField4.style.display = 'block';
      }
      // C (Complete graph) has no parameters
  }

  // Display network file name when selected
  function displayNetworkFileNameCreate(input) {
      const display = document.getElementById('network-file-name-display-create');
      if (input.files && input.files[0]) {
          display.textContent = '✓ ' + input.files[0].name;
          display.style.display = 'block';
      } else {
          display.textContent = '';
          display.style.display = 'none';
      }
      updateNetworkInputStates();
  }

  // On page load, disable image action by default and setup form validation
  document.addEventListener('DOMContentLoaded', function() {
      if (YS_DATA_CLIENTS.llmAgentsEnabled) {
      disableImageAction();
      } else {
      // When LLM agents are disabled, enable image action automatically
      enableImageAction();
      }
    
      // Initialize button state based on backend
      const backendSelect = document.getElementById('llm_backend');
      const submitButton = document.getElementById('create_client_button');
    
      if (!YS_DATA_CLIENTS.llmAgentsEnabled) {
      // When LLM agents are disabled, enable submit button immediately
      if (submitButton) {
          submitButton.disabled = false;
      }
      } else {
      // When LLM agents are enabled, update state based on backend
      if (backendSelect) {
          updateFormButtonStateForBackend(backendSelect.value);
      }
      }
    
      // Setup form button state management
      const modelsSelect = document.getElementById('models_select_client');
    
      if (YS_DATA_CLIENTS.llmAgentsEnabled) {
      if (modelsSelect) {
          // Monitor model selection
          modelsSelect.addEventListener('change', function() {
              llmModelSelected = this.value !== '';
              updateFormButtonState();
          });
      }
      }
    
      // Setup network mutual exclusivity
      const networkModelSelect = document.getElementById('network_model_select');
      const networkFileInput = document.getElementById('network_file_create');
    
      if (networkModelSelect) {
          networkModelSelect.addEventListener('change', updateNetworkInputStates);
      }
      if (networkFileInput) {
          networkFileInput.addEventListener('change', function() {
              displayNetworkFileNameCreate(this);
          });
      }
    
      // Initial state
      updateNetworkInputStates();
    
      // Handle Explorer archetype based on follow probabilities

      // Handle archetype toggle
      const archetypeToggle = document.getElementById('enable_archetypes');
      const archetypeDetails = document.getElementById('archetype-details');
      const agentDowncastCheckbox = document.getElementById('agent_downcast');
    
      function updateArchetypeToggle() {
          if (!archetypeToggle || !archetypeDetails) return;
        
          if (archetypeToggle.checked) {
              // Enable archetypes
              archetypeDetails.style.opacity = '1';
              archetypeDetails.style.pointerEvents = 'auto';
            
              // Enable agent downcast only if LLM agents are enabled
              if (YS_DATA_CLIENTS.llmAgentsEnabled) {
              if (agentDowncastCheckbox) {
                  agentDowncastCheckbox.disabled = false;
                  agentDowncastCheckbox.parentElement.style.opacity = '1';
                  agentDowncastCheckbox.parentElement.style.cursor = 'pointer';
              }
              }
          } else {
              // Disable archetypes
              archetypeDetails.style.opacity = '0.5';
              archetypeDetails.style.pointerEvents = 'none';
              // Close the details if open
              archetypeDetails.open = false;
            
              // Disable agent downcast when archetypes are disabled
              if (agentDowncastCheckbox) {
                  agentDowncastCheckbox.disabled = true;
                  agentDowncastCheckbox.checked = false;
                  agentDowncastCheckbox.parentElement.style.opacity = '0.5';
                  agentDowncastCheckbox.parentElement.style.cursor = 'not-allowed';
              }
          }
      }
    
      if (archetypeToggle) {
          archetypeToggle.addEventListener('change', updateArchetypeToggle);
          // Initial state
          updateArchetypeToggle();
      }
    
      // Handle agent downcast based on LLM agents enabled status
      if (!YS_DATA_CLIENTS.llmAgentsEnabled) {
      // When LLM agents are disabled, agent downcast must also be disabled
      if (agentDowncastCheckbox) {
          agentDowncastCheckbox.disabled = true;
          agentDowncastCheckbox.checked = false;
          agentDowncastCheckbox.parentElement.style.opacity = '0.5';
          agentDowncastCheckbox.parentElement.style.cursor = 'not-allowed';
      }
      }
  });

  // Sync display input with hidden input
  document.getElementById('days_display').addEventListener('change', function() {
      document.getElementById('days_input').value = this.value;
  });
  document.getElementById('days_display').addEventListener('input', function() {
      document.getElementById('days_input').value = this.value;
  });

  // Toggle between finite and infinite duration
  document.getElementById('infinite_duration').addEventListener('change', function() {
      const daysDisplay = document.getElementById('days_display');
      const daysInput = document.getElementById('days_input');
      const defaultDays = '30';
      if (this.checked) {
          // Store current value before switching to infinite
          daysDisplay.dataset.previousValue = daysDisplay.value;
          daysDisplay.value = '∞';
          daysDisplay.disabled = true;
          daysDisplay.style.opacity = '0.5';
          daysInput.value = -1;
      } else {
          // Restore previous value or use default
          daysDisplay.value = daysDisplay.dataset.previousValue || defaultDays;
          daysDisplay.disabled = false;
          daysDisplay.style.opacity = '1';
          daysInput.value = daysDisplay.value;
      }
  });

  // Initialize chart with default data
  function initActivityChart() {
      const defaultData = [
          0.023, 0.021, 0.020, 0.020, 0.018, 0.017, 0.017, 0.018,
          0.020, 0.020, 0.021, 0.022, 0.024, 0.027, 0.030, 0.032,
          0.032, 0.032, 0.032, 0.031, 0.030, 0.029, 0.027, 0.025
      ];
      const labels = Array.from({length: 24}, (_, i) => i.toString());
    
      // Convert to percentages
      const activityData = defaultData.map(v => v * 100);
      const maxValue = Math.max(...activityData);
      const yAxisMax = Math.ceil(maxValue * 1.1);

      const ctx = document.getElementById('activity_rates_create');
      if (!ctx) return;

      new Chart(ctx, {
          type: 'bar',
          data: {
              labels: labels,
              datasets: [{
                  label: 'Activity %',
                  data: activityData,
                  backgroundColor: 'rgba(34, 197, 94, 0.6)',
                  borderColor: 'rgba(34, 197, 94, 1)',
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
                              return 'Active: ' + context.parsed.y.toFixed(2) + '%';
                          }
                      }
                  }
              },
              scales: {
                  y: {
                      beginAtZero: true,
                      suggestedMax: yAxisMax,
                      ticks: {
                          font: { size: 10 },
                          callback: function(value) {
                              return value + '%';
                          }
                      },
                      grid: {
                          color: 'rgba(0, 0, 0, 0.05)'
                      }
                  },
                  x: {
                      ticks: {
                          font: { size: 9 }
                      },
                      grid: {
                          display: false
                      }
                  }
              }
          }
      });
  }

  // Initialize chart when details are expanded
  document.addEventListener('DOMContentLoaded', function() {
      const detailsElements = document.querySelectorAll('details');
      detailsElements.forEach(details => {
          details.addEventListener('toggle', function() {
              if (this.open && this.querySelector('#activity_rates_create')) {
                  setTimeout(initActivityChart, 100);
              }
          });
      });
  });

                                              document.querySelectorAll('.number-scale').forEach(scale => {
                                                const boxes = scale.querySelectorAll('.number-box');
                                                const wrapper = scale.closest('.scale-wrapper');
                                                const hiddenInput = wrapper.querySelector('input[type="hidden"]');

                                                boxes.forEach(box => {
                                                  box.addEventListener('click', () => {
                                                    boxes.forEach(b => b.classList.remove('selected'));
                                                    box.classList.add('selected');
                                                    hiddenInput.value = box.dataset.value;
                                                    display.textContent = box.dataset.value;
                                                  });
                                                });
                                              });

  // Track if models have been fetched and validated
  let llmModelsFetched = false;
  let llmModelSelected = false;

  // Enable disabled inputs before form submission so their values are included

  // Check if form should be enabled
  function updateFormButtonState() {
      const submitButton = document.getElementById('create_client_button');
      if (submitButton) {
          if (YS_DATA_CLIENTS.llmAgentsEnabled) {
          submitButton.disabled = !(llmModelsFetched && llmModelSelected);
          } else {
          // When LLM agents are disabled, form can be submitted without LLM validation
          submitButton.disabled = false;
          }
      }
  }

  // Fetch models for client LLM configuration
  function fetchModelsForClient() {
      const urlInput = document.getElementById('custom_llm_url_client');
      const select = document.getElementById('models_select_client');
      const status = document.getElementById('llm_url_status_client');
      const llmUrl = urlInput.value.trim();
    
      if (!llmUrl) {
          alert('Please enter an LLM server URL');
          return;
      }
    
      status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Fetching...';
    
      fetch(`/admin/api/fetch_models?llm_url=${encodeURIComponent(llmUrl)}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                  llmModelsFetched = false;
                  updateFormButtonState();
                  setTimeout(() => { status.innerHTML = ''; }, 5000);
              } else {
                  select.innerHTML = '<option value="">Select a model</option>';
                  data.models.forEach(model => {
                      const option = document.createElement('option');
                      option.value = model;
                      option.textContent = model;
                      select.appendChild(option);
                  });
                  status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> ' + data.models.length + ' models loaded</span>';
                  llmModelsFetched = true;
                  // Reset model selection since we just loaded new models
                  llmModelSelected = false;
                  updateFormButtonState();
                  setTimeout(() => { status.innerHTML = ''; }, 3000);
              }
          })
          .catch(error => {
              status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
              llmModelsFetched = false;
              updateFormButtonState();
              setTimeout(() => { status.innerHTML = ''; }, 5000);
          });
  }

  // Validate that minicpm-v:latest is available for image transcription
  function validateImageLLMModel() {
      const llmVUrlInput = document.getElementById('custom_llm_url_v_client');
      const status = document.getElementById('llm_v_url_status_client');
      const validationStatus = document.getElementById('llm_v_validation_status');
      const llmVUrl = llmVUrlInput.value.trim();
      const modelName = 'minicpm-v:latest';
    
      if (!llmVUrl) {
          alert('Please enter an LLM server URL for image transcription');
          return;
      }
    
      status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Validating...';
    
      fetch(`/admin/api/fetch_models?llm_url=${encodeURIComponent(llmVUrl)}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                  validationStatus.value = 'false';
                  disableImageAction();
                  alert('Unable to connect to the LLM server. Image sharing/commenting functionality will remain disabled.');
                  setTimeout(() => { status.innerHTML = ''; }, 5000);
              } else {
                  // Check if minicpm-v:latest model exists in fetched models
                  const modelExists = data.models.includes(modelName);
                
                  if (modelExists) {
                      status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> Model "' + modelName + '" found and validated!</span>';
                      validationStatus.value = 'true';
                      enableImageAction();
                      setTimeout(() => { status.innerHTML = ''; }, 3000);
                  } else {
                      status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Model "' + modelName + '" not found on this server!</span>';
                      validationStatus.value = 'false';
                      disableImageAction();
                      alert('The minicpm-v:latest model is not available on the specified server. Image sharing/commenting functionality will remain disabled.');
                  }
              }
          })
          .catch(error => {
              status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
              validationStatus.value = 'false';
              disableImageAction();
              alert('Failed to connect to the LLM server. Image sharing/commenting functionality will remain disabled.');
              setTimeout(() => { status.innerHTML = ''; }, 5000);
          });
  }

  // Disable the "Share and comment an Image" action
  function disableImageAction() {
      const imageScale = document.getElementById('image');
      const imageScaleWrapper = imageScale ? imageScale.closest('.scale-wrapper') : null;
      const warning = document.getElementById('image_action_warning');
    
      if (imageScaleWrapper) {
          const numberBoxes = imageScaleWrapper.querySelectorAll('.number-box');
          numberBoxes.forEach(box => {
              if (box.dataset.value !== '0') {
                  box.style.opacity = '0.3';
                  box.style.pointerEvents = 'none';
                  box.style.cursor = 'not-allowed';
              }
          });
        
          // Force selection to 0
          numberBoxes.forEach(box => box.classList.remove('selected'));
          numberBoxes[0].classList.add('selected');
          imageScale.value = '0';
      }
    
      if (warning) {
          warning.style.display = 'block';
      }
  }

  // Enable the "Share and comment an Image" action
  function enableImageAction() {
      const imageScale = document.getElementById('image');
      const imageScaleWrapper = imageScale ? imageScale.closest('.scale-wrapper') : null;
      const warning = document.getElementById('image_action_warning');
    
      if (imageScaleWrapper) {
          const numberBoxes = imageScaleWrapper.querySelectorAll('.number-box');
          numberBoxes.forEach(box => {
              box.style.opacity = '1';
              box.style.pointerEvents = 'auto';
              box.style.cursor = 'pointer';
          });
      }
    
      if (warning) {
          warning.style.display = 'none';
      }
  }

  // Handle mutual exclusivity between synthetic network and file upload
  function updateNetworkInputStates() {
      const networkModelSelect = document.getElementById('network_model_select');
      const networkFileInput = document.getElementById('network_file_create');
      const networkFileLabel = document.querySelector('.file-upload-label-network-create');
      const erParamField = document.getElementById('er_param_field');
      const baParamField = document.getElementById('ba_param_field');
      const wsParamField = document.getElementById('ws_param_field');
      const wsParamField2 = document.getElementById('ws_param_field2');
      const plcParamField = document.getElementById('plc_param_field');
      const plcParamField2 = document.getElementById('plc_param_field2');
      const sbmParamField = document.getElementById('sbm_param_field');
      const sbmParamField2 = document.getElementById('sbm_param_field2');
      const sbmParamField3 = document.getElementById('sbm_param_field3');
      const lfrParamField = document.getElementById('lfr_param_field');
      const lfrParamField2 = document.getElementById('lfr_param_field2');
      const lfrParamField3 = document.getElementById('lfr_param_field3');
      const lfrParamField4 = document.getElementById('lfr_param_field4');
    
      if (!networkModelSelect || !networkFileInput) return;
    
      const modelSelected = networkModelSelect.value !== '';
      const fileSelected = networkFileInput.files && networkFileInput.files.length > 0;
    
      // If synthetic model is selected, disable file upload
      if (modelSelected) {
          networkFileInput.disabled = true;
          if (networkFileLabel) {
              networkFileLabel.classList.add('disabled');
          }
      } else {
          networkFileInput.disabled = false;
          if (networkFileLabel) {
              networkFileLabel.classList.remove('disabled');
          }
      }
    
      // If file is uploaded, disable synthetic model selection
      if (fileSelected) {
          networkModelSelect.disabled = true;
      } else {
          networkModelSelect.disabled = false;
      }
    
      // Show/hide parameter fields based on model selection
      if (erParamField) erParamField.style.display = 'none';
      if (baParamField) baParamField.style.display = 'none';
      if (wsParamField) wsParamField.style.display = 'none';
      if (wsParamField2) wsParamField2.style.display = 'none';
      if (plcParamField) plcParamField.style.display = 'none';
      if (plcParamField2) plcParamField2.style.display = 'none';
      if (sbmParamField) sbmParamField.style.display = 'none';
      if (sbmParamField2) sbmParamField2.style.display = 'none';
      if (sbmParamField3) sbmParamField3.style.display = 'none';
      if (lfrParamField) lfrParamField.style.display = 'none';
      if (lfrParamField2) lfrParamField2.style.display = 'none';
      if (lfrParamField3) lfrParamField3.style.display = 'none';
      if (lfrParamField4) lfrParamField4.style.display = 'none';
    
      if (networkModelSelect.value === 'ER' && erParamField) {
          erParamField.style.display = 'block';
      } else if (networkModelSelect.value === 'BA' && baParamField) {
          baParamField.style.display = 'block';
      } else if (networkModelSelect.value === 'WS') {
          if (wsParamField) wsParamField.style.display = 'block';
          if (wsParamField2) wsParamField2.style.display = 'block';
      } else if (networkModelSelect.value === 'PLC') {
          if (plcParamField) plcParamField.style.display = 'block';
          if (plcParamField2) plcParamField2.style.display = 'block';
      } else if (networkModelSelect.value === 'SBM') {
          if (sbmParamField) sbmParamField.style.display = 'block';
          if (sbmParamField2) sbmParamField2.style.display = 'block';
          if (sbmParamField3) sbmParamField3.style.display = 'block';
      } else if (networkModelSelect.value === 'LFR') {
          if (lfrParamField) lfrParamField.style.display = 'block';
          if (lfrParamField2) lfrParamField2.style.display = 'block';
          if (lfrParamField3) lfrParamField3.style.display = 'block';
          if (lfrParamField4) lfrParamField4.style.display = 'block';
      }
      // C (Complete graph) has no parameters
  }

  // Display network file name when selected
  function displayNetworkFileNameCreate(input) {
      const display = document.getElementById('network-file-name-display-create');
      if (input.files && input.files[0]) {
          display.textContent = '✓ ' + input.files[0].name;
          display.style.display = 'block';
      } else {
          display.textContent = '';
          display.style.display = 'none';
      }
      updateNetworkInputStates();
  }

  function toggleSimulationAdvancedParams() {
      const checkbox = document.getElementById('show_simulation_advanced_params');
      const fields = document.getElementById('simulation_advanced_params_fields');
    
      if (checkbox && fields) {
          fields.style.display = checkbox.checked ? 'block' : 'none';
      }
  }

  function toggleStandardMemorySettings() {
      const checkbox = document.getElementById('standard_memory_enabled');
      const fields = document.getElementById('standard_memory_config_fields');
      const advancedCheckbox = document.getElementById('show_standard_memory_advanced_params');
      const advancedFields = document.getElementById('standard_memory_advanced_params_fields');

      if (!checkbox || !fields) return;

      fields.style.display = checkbox.checked ? 'block' : 'none';
      fields.querySelectorAll('input, select, textarea').forEach((control) => {
          if (control.id === 'standard_memory_enabled') return;
          control.disabled = !checkbox.checked;
      });

      if (!checkbox.checked) {
          if (advancedCheckbox) {
              advancedCheckbox.checked = false;
          }
          if (advancedFields) {
              advancedFields.style.display = 'none';
          }
      }

      toggleStandardMemoryAdvancedParams();
      syncStandardEmbeddingFieldsState();
  }

  function toggleStandardMemoryAdvancedParams() {
      const checkbox = document.getElementById('show_standard_memory_advanced_params');
      const memoryToggle = document.getElementById('standard_memory_enabled');
      const fields = document.getElementById('standard_memory_advanced_params_fields');
      if (!checkbox || !fields) return;
      fields.style.display = checkbox.checked && memoryToggle && memoryToggle.checked ? 'block' : 'none';
  }

  function syncStandardEmbeddingFieldsState() {
      const memoryToggle = document.getElementById('standard_memory_enabled');
      const semanticToggle = document.getElementById('standard_memory_semantic_enabled');
      const embeddingModel = document.getElementById('standard_memory_embedding_model');
      const embeddingAsync = document.getElementById('standard_memory_embedding_async');
      const enabled = !!(memoryToggle && memoryToggle.checked && semanticToggle && semanticToggle.checked);

      if (embeddingModel) {
          embeddingModel.disabled = !enabled;
      }
      if (embeddingAsync) {
          embeddingAsync.disabled = !enabled;
          if (!enabled) {
              embeddingAsync.checked = false;
          }
      }
  }

  // On page load, disable image action by default and setup form validation
  document.addEventListener('DOMContentLoaded', function() {
      if (YS_DATA_CLIENTS.llmAgentsEnabled) {
      disableImageAction();
      } else {
      // When LLM agents are disabled, enable image action automatically
      enableImageAction();
      }
    
      // Setup form button state management
      const modelsSelect = document.getElementById('models_select_client');
      const submitButton = document.getElementById('create_client_button');
    
      // Ensure button is disabled initially
      if (submitButton) {
          if (YS_DATA_CLIENTS.llmAgentsEnabled) {
          submitButton.disabled = true;
          } else {
          // When LLM agents are disabled, form can be submitted immediately
          submitButton.disabled = false;
          }
      }
    
      if (YS_DATA_CLIENTS.llmAgentsEnabled) {
      if (modelsSelect) {
          // Monitor model selection
          modelsSelect.addEventListener('change', function() {
              llmModelSelected = this.value !== '';
              updateFormButtonState();
          });
      }
      }
    
      // Setup network mutual exclusivity
      const networkModelSelect = document.getElementById('network_model_select');
      const networkFileInput = document.getElementById('network_file_create');
    
      if (networkModelSelect) {
          networkModelSelect.addEventListener('change', updateNetworkInputStates);
      }
      if (networkFileInput) {
          networkFileInput.addEventListener('change', function() {
              displayNetworkFileNameCreate(this);
          });
      }
    
      // Initial state
      updateNetworkInputStates();
    

      // Handle archetype toggle
      const archetypeToggle = document.getElementById('enable_archetypes');
      const archetypeDetails = document.getElementById('archetype-details');
    
      function updateArchetypeToggle() {
          if (!archetypeToggle || !archetypeDetails) return;
        
          if (archetypeToggle.checked) {
              // Enable archetypes
              archetypeDetails.style.opacity = '1';
              archetypeDetails.style.pointerEvents = 'auto';
          } else {
              // Disable archetypes
              archetypeDetails.style.opacity = '0.5';
              archetypeDetails.style.pointerEvents = 'none';
              // Close the details if open
              archetypeDetails.open = false;
          }
      }
    
      if (archetypeToggle) {
          archetypeToggle.addEventListener('change', updateArchetypeToggle);
          // Initial state
          updateArchetypeToggle();
      }
    
      // Initialize simulation advanced params state
      toggleSimulationAdvancedParams();
      toggleStandardMemorySettings();
      toggleStandardMemoryAdvancedParams();
      syncStandardEmbeddingFieldsState();
  });

  // Sync display input with hidden input
  document.getElementById('days_display').addEventListener('change', function() {
      document.getElementById('days_input').value = this.value;
  });
  document.getElementById('days_display').addEventListener('input', function() {
      document.getElementById('days_input').value = this.value;
  });

  // Toggle between finite and infinite duration
  document.getElementById('infinite_duration').addEventListener('change', function() {
      const daysDisplay = document.getElementById('days_display');
      const daysInput = document.getElementById('days_input');
      const defaultDays = '30';
      if (this.checked) {
          // Store current value before switching to infinite
          daysDisplay.dataset.previousValue = daysDisplay.value;
          daysDisplay.value = '∞';
          daysDisplay.disabled = true;
          daysDisplay.style.opacity = '0.5';
          daysInput.value = -1;
      } else {
          // Restore previous value or use default
          daysDisplay.value = daysDisplay.dataset.previousValue || defaultDays;
          daysDisplay.disabled = false;
          daysDisplay.style.opacity = '1';
          daysInput.value = daysDisplay.value;
      }
  });

  // Initialize chart with default data
  function initActivityChart() {
      const defaultData = [
          0.023, 0.021, 0.020, 0.020, 0.018, 0.017, 0.017, 0.018,
          0.020, 0.020, 0.021, 0.022, 0.024, 0.027, 0.030, 0.032,
          0.032, 0.032, 0.032, 0.031, 0.030, 0.029, 0.027, 0.025
      ];
      const labels = Array.from({length: 24}, (_, i) => i.toString());
    
      // Convert to percentages
      const activityData = defaultData.map(v => v * 100);
      const maxValue = Math.max(...activityData);
      const yAxisMax = Math.ceil(maxValue * 1.1);

      const ctx = document.getElementById('activity_rates_create');
      if (!ctx) return;

      new Chart(ctx, {
          type: 'bar',
          data: {
              labels: labels,
              datasets: [{
                  label: 'Activity %',
                  data: activityData,
                  backgroundColor: 'rgba(34, 197, 94, 0.6)',
                  borderColor: 'rgba(34, 197, 94, 1)',
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
                              return 'Active: ' + context.parsed.y.toFixed(2) + '%';
                          }
                      }
                  }
              },
              scales: {
                  y: {
                      beginAtZero: true,
                      suggestedMax: yAxisMax,
                      ticks: {
                          font: { size: 10 },
                          callback: function(value) {
                              return value + '%';
                          }
                      },
                      grid: {
                          color: 'rgba(0, 0, 0, 0.05)'
                      }
                  },
                  x: {
                      ticks: {
                          font: { size: 9 }
                      },
                      grid: {
                          display: false
                      }
                  }
              }
          }
      });
  }

  // Initialize chart when details are expanded
  document.addEventListener('DOMContentLoaded', function() {
      const detailsElements = document.querySelectorAll('details');
      detailsElements.forEach(details => {
          details.addEventListener('toggle', function() {
              if (this.open && this.querySelector('#activity_rates_create')) {
                  setTimeout(initActivityChart, 100);
              }
          });
      });
  });

  document.querySelectorAll('.number-scale').forEach(scale => {
      const boxes = scale.querySelectorAll('.number-box');
      const wrapper = scale.closest('.scale-wrapper');
      const hiddenInput = wrapper.querySelector('input[type="hidden"]');
      const scaleFactor = parseFloat(wrapper.dataset.scaleFactor || '1');

      boxes.forEach(box => {
          box.addEventListener('click', () => {
              boxes.forEach(b => b.classList.remove('selected'));
              box.classList.add('selected');
              hiddenInput.value = String(parseFloat(box.dataset.value) * scaleFactor);
          });
      });
  });

  // Track if models have been fetched and validated
  let llmModelsFetched = false;
  let llmModelSelected = false;

  // Check if form should be enabled
  function updateFormButtonState() {
      const submitButton = document.getElementById('create_client_button');
      if (submitButton) {
          if (YS_DATA_CLIENTS.llmAgentsEnabled) {
          submitButton.disabled = !(llmModelsFetched && llmModelSelected);
          } else {
          // When LLM agents are disabled, form can be submitted without LLM validation
          submitButton.disabled = false;
          }
      }
  }

  function setNumericInputByName(name, value) {
      const input = document.querySelector(`input[name="${name}"]`);
      if (!input) return;
      input.value = String(value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function applyContextPreset() {
      const presetSelect = document.getElementById('context_preset_select');
      const status = document.getElementById('context_preset_status');
      if (!presetSelect) return;

      const presets = {
          balanced: {
              max_thread_context_chars: 3200,
              memory_prompt_max_chars: 1600,
              memory_search_max_chars: 900,
              memory_tier_a_max_chars: 350,
              memory_tier_b_max_chars: 900,
              memory_tier_c_max_chars: 900,
              memory_total_max_chars: 2200,
              llm_max_tokens: 768,
          },
          high_24b: {
              max_thread_context_chars: 4200,
              memory_prompt_max_chars: 2200,
              memory_search_max_chars: 1200,
              memory_tier_a_max_chars: 450,
              memory_tier_b_max_chars: 1200,
              memory_tier_c_max_chars: 1200,
              memory_total_max_chars: 3000,
              llm_max_tokens: 1024,
          },
      };

      const preset = presets[presetSelect.value];
      if (!preset) return;

      Object.entries(preset).forEach(([name, value]) => {
          setNumericInputByName(name, value);
      });

      if (status) {
          const label = presetSelect.options[presetSelect.selectedIndex].text;
          status.textContent = `Applied: ${label}`;
          status.style.display = 'block';
          setTimeout(() => {
              status.style.display = 'none';
          }, 2500);
      }
  }

  // Fetch models for client LLM configuration
  function fetchModelsForClient() {
      const urlInput = document.getElementById('custom_llm_url_client');
      const select = document.getElementById('models_select_client');
      const status = document.getElementById('llm_url_status_client');
      const llmUrl = urlInput.value.trim();
    
      if (!llmUrl) {
          alert('Please enter an LLM server URL');
          return;
      }
    
      status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Fetching...';
    
      fetch(`/admin/api/fetch_models?llm_url=${encodeURIComponent(llmUrl)}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                  llmModelsFetched = false;
                  updateFormButtonState();
                  setTimeout(() => { status.innerHTML = ''; }, 5000);
              } else {
                  select.innerHTML = '<option value="">Select a model</option>';
                  data.models.forEach(model => {
                      const option = document.createElement('option');
                      option.value = model;
                      option.textContent = model;
                      select.appendChild(option);
                  });
                  status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> ' + data.models.length + ' models loaded</span>';
                  llmModelsFetched = true;
                  // Reset model selection since we just loaded new models
                  llmModelSelected = false;
                  updateFormButtonState();
                  setTimeout(() => { status.innerHTML = ''; }, 3000);
              }
          })
          .catch(error => {
              status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
              llmModelsFetched = false;
              updateFormButtonState();
              setTimeout(() => { status.innerHTML = ''; }, 5000);
          });
  }

  // Validate that selected VLM model is available for image transcription
  function validateImageLLMModel() {
      const llmVUrlInput = document.getElementById('custom_llm_url_v_client');
      const status = document.getElementById('llm_v_url_status_client');
      const validationStatus = document.getElementById('llm_v_validation_status');
      const llmVUrl = llmVUrlInput.value.trim();
      const modelSelect = document.getElementById('llm_v_agent');
      const modelName = modelSelect.value;
    
      if (!llmVUrl) {
          alert('Please enter an LLM server URL for image transcription');
          return;
      }
    
      status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Validating...';
    
      fetch(`/admin/api/fetch_models?llm_url=${encodeURIComponent(llmVUrl)}`)
          .then(response => response.json())
          .then(data => {
              if (data.error) {
                  status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                  validationStatus.value = 'false';
                  disableImageAction();
                  alert('Unable to connect to the LLM server. Image sharing/commenting functionality will remain disabled.');
                  setTimeout(() => { status.innerHTML = ''; }, 5000);
              } else {
                  // Check if selected VLM model exists in fetched models
                  const modelExists = data.models.includes(modelName);

                  if (modelExists) {
                      status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> Model "' + modelName + '" found and validated!</span>';
                      validationStatus.value = 'true';
                      enableImageAction();
                      setTimeout(() => { status.innerHTML = ''; }, 3000);
                  } else {
                      status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Model "' + modelName + '" not found on this server!</span>';
                      validationStatus.value = 'false';
                      disableImageAction();
                      alert('The "' + modelName + '" model is not available on the specified server. Image sharing/commenting functionality will remain disabled.');
                      // Set llm_v to empty/None to signal model unavailability
                      llmVUrlInput.value = '';
                  }
              }
          })
          .catch(error => {
              status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
              validationStatus.value = 'false';
              disableImageAction();
              alert('Failed to connect to the LLM server. Image sharing/commenting functionality will remain disabled.');
              setTimeout(() => { status.innerHTML = ''; }, 5000);
          });
  }

  // Disable the "Share and comment an Image" action
  function disableImageAction() {
      const imageScale = document.getElementById('image');
      const imageScaleWrapper = imageScale ? imageScale.closest('.scale-wrapper') : null;
      const warning = document.getElementById('image_action_warning');
    
      if (imageScaleWrapper) {
          const numberBoxes = imageScaleWrapper.querySelectorAll('.number-box');
          numberBoxes.forEach(box => {
              if (box.dataset.value !== '0') {
                  box.style.opacity = '0.3';
                  box.style.pointerEvents = 'none';
                  box.style.cursor = 'not-allowed';
              }
          });
        
          // Force selection to 0
          numberBoxes.forEach(box => box.classList.remove('selected'));
          numberBoxes[0].classList.add('selected');
          imageScale.value = '0';
      }
    
      if (warning) {
          warning.style.display = 'block';
      }
  }

  // Enable the "Share and comment an Image" action
  function enableImageAction() {
      const imageScale = document.getElementById('image');
      const imageScaleWrapper = imageScale ? imageScale.closest('.scale-wrapper') : null;
      const warning = document.getElementById('image_action_warning');
    
      if (imageScaleWrapper) {
          const numberBoxes = imageScaleWrapper.querySelectorAll('.number-box');
          numberBoxes.forEach(box => {
              box.style.opacity = '1';
              box.style.pointerEvents = 'auto';
              box.style.cursor = 'pointer';
          });
      }
    
      if (warning) {
          warning.style.display = 'none';
      }
  }

  // Handle mutual exclusivity between synthetic network and file upload
  function updateNetworkInputStates() {
      const networkModelSelect = document.getElementById('network_model_select');
      const networkFileInput = document.getElementById('network_file_create');
      const networkFileLabel = document.querySelector('.file-upload-label-network-create');
      const erParamField = document.getElementById('er_param_field');
      const baParamField = document.getElementById('ba_param_field');
      const wsParamField = document.getElementById('ws_param_field');
      const wsParamField2 = document.getElementById('ws_param_field2');
      const plcParamField = document.getElementById('plc_param_field');
      const plcParamField2 = document.getElementById('plc_param_field2');
      const sbmParamField = document.getElementById('sbm_param_field');
      const sbmParamField2 = document.getElementById('sbm_param_field2');
      const sbmParamField3 = document.getElementById('sbm_param_field3');
      const lfrParamField = document.getElementById('lfr_param_field');
      const lfrParamField2 = document.getElementById('lfr_param_field2');
      const lfrParamField3 = document.getElementById('lfr_param_field3');
      const lfrParamField4 = document.getElementById('lfr_param_field4');
    
      if (!networkModelSelect || !networkFileInput) return;
    
      const modelSelected = networkModelSelect.value !== '';
      const fileSelected = networkFileInput.files && networkFileInput.files.length > 0;
    
      // If synthetic model is selected, disable file upload
      if (modelSelected) {
          networkFileInput.disabled = true;
          if (networkFileLabel) {
              networkFileLabel.classList.add('disabled');
          }
      } else {
          networkFileInput.disabled = false;
          if (networkFileLabel) {
              networkFileLabel.classList.remove('disabled');
          }
      }
    
      // If file is uploaded, disable synthetic model selection
      if (fileSelected) {
          networkModelSelect.disabled = true;
      } else {
          networkModelSelect.disabled = false;
      }
    
      // Show/hide parameter fields based on model selection
      if (erParamField) erParamField.style.display = 'none';
      if (baParamField) baParamField.style.display = 'none';
      if (wsParamField) wsParamField.style.display = 'none';
      if (wsParamField2) wsParamField2.style.display = 'none';
      if (plcParamField) plcParamField.style.display = 'none';
      if (plcParamField2) plcParamField2.style.display = 'none';
      if (sbmParamField) sbmParamField.style.display = 'none';
      if (sbmParamField2) sbmParamField2.style.display = 'none';
      if (sbmParamField3) sbmParamField3.style.display = 'none';
      if (lfrParamField) lfrParamField.style.display = 'none';
      if (lfrParamField2) lfrParamField2.style.display = 'none';
      if (lfrParamField3) lfrParamField3.style.display = 'none';
      if (lfrParamField4) lfrParamField4.style.display = 'none';
    
      if (networkModelSelect.value === 'ER' && erParamField) {
          erParamField.style.display = 'block';
      } else if (networkModelSelect.value === 'BA' && baParamField) {
          baParamField.style.display = 'block';
      } else if (networkModelSelect.value === 'WS') {
          if (wsParamField) wsParamField.style.display = 'block';
          if (wsParamField2) wsParamField2.style.display = 'block';
      } else if (networkModelSelect.value === 'PLC') {
          if (plcParamField) plcParamField.style.display = 'block';
          if (plcParamField2) plcParamField2.style.display = 'block';
      } else if (networkModelSelect.value === 'SBM') {
          if (sbmParamField) sbmParamField.style.display = 'block';
          if (sbmParamField2) sbmParamField2.style.display = 'block';
          if (sbmParamField3) sbmParamField3.style.display = 'block';
      } else if (networkModelSelect.value === 'LFR') {
          if (lfrParamField) lfrParamField.style.display = 'block';
          if (lfrParamField2) lfrParamField2.style.display = 'block';
          if (lfrParamField3) lfrParamField3.style.display = 'block';
          if (lfrParamField4) lfrParamField4.style.display = 'block';
      }
      // C (Complete graph) has no parameters
  }

  // Display network file name when selected
  function displayNetworkFileNameCreate(input) {
      const display = document.getElementById('network-file-name-display-create');
      if (input.files && input.files[0]) {
          display.textContent = '✓ ' + input.files[0].name;
          display.style.display = 'block';
      } else {
          display.textContent = '';
          display.style.display = 'none';
      }
      updateNetworkInputStates();
  }

  function toggleSimulationAdvancedParams() {
      const checkbox = document.getElementById('show_simulation_advanced_params');
      const fields = document.getElementById('simulation_advanced_params_fields');

      if (checkbox && fields) {
          fields.style.display = checkbox.checked ? 'block' : 'none';
      }
  }

  function toggleForumMemorySettings() {
      const checkbox = document.getElementById('memory_enabled');
      const fields = document.getElementById('forum_memory_config_fields');
      const advancedCheckbox = document.getElementById('show_memory_advanced_params');
      const advancedFields = document.getElementById('memory_advanced_params_fields');

      if (!checkbox || !fields) {
          return;
      }

      const enabled = checkbox.checked;
      fields.style.display = enabled ? 'block' : 'none';

      const controls = fields.querySelectorAll('input, select, textarea, button');
      controls.forEach(control => {
          if (control.id === 'memory_enabled') {
              return;
          }
          control.disabled = !enabled;
      });

      if (enabled) {
          syncForumMemoryControls();
          toggleForumMemoryAdvancedParams();
      } else {
          if (advancedCheckbox) {
              advancedCheckbox.checked = false;
          }
          if (advancedFields) {
              advancedFields.style.display = 'none';
          }
      }
  }

  function toggleForumMemoryAdvancedParams() {
      const checkbox = document.getElementById('show_memory_advanced_params');
      const memoryToggle = document.getElementById('memory_enabled');
      const fields = document.getElementById('memory_advanced_params_fields');

      if (!checkbox || !fields) {
          return;
      }

      const enabled = !!(memoryToggle && memoryToggle.checked && checkbox.checked);
      fields.style.display = enabled ? 'block' : 'none';
  }

  function syncForumMemoryControls() {
      const memoryToggle = document.getElementById('memory_enabled');
      const semanticToggle = document.getElementById('memory_semantic_enabled');
      const embeddingModel = document.getElementById('memory_embedding_model');
      const embeddingAsync = document.getElementById('memory_embedding_async');
      const memoryEnabled = !!(memoryToggle && memoryToggle.checked);
      const enabled = memoryEnabled && !!(semanticToggle && semanticToggle.checked);

      if (embeddingModel) {
          embeddingModel.disabled = !enabled;
      }
      if (embeddingAsync) {
          embeddingAsync.disabled = !enabled;
          if (!enabled) {
              embeddingAsync.checked = false;
          }
      }
  }

  // On page load, disable image action by default and setup form validation
  document.addEventListener('DOMContentLoaded', function() {
      if (YS_DATA_CLIENTS.llmAgentsEnabled) {
      disableImageAction();
      } else {
      // When LLM agents are disabled, enable image action automatically
      enableImageAction();
      }
    
      // Setup form button state management
      const modelsSelect = document.getElementById('models_select_client');
      const submitButton = document.getElementById('create_client_button');
    
      // Ensure button is disabled initially
      if (submitButton) {
          if (YS_DATA_CLIENTS.llmAgentsEnabled) {
          submitButton.disabled = true;
          } else {
          // When LLM agents are disabled, form can be submitted immediately
          submitButton.disabled = false;
          }
      }
    
      if (YS_DATA_CLIENTS.llmAgentsEnabled) {
      if (modelsSelect) {
          // Monitor model selection
          modelsSelect.addEventListener('change', function() {
              llmModelSelected = this.value !== '';
              updateFormButtonState();
          });
      }
      }
    
      // Setup network mutual exclusivity
      const networkModelSelect = document.getElementById('network_model_select');
      const networkFileInput = document.getElementById('network_file_create');
    
      if (networkModelSelect) {
          networkModelSelect.addEventListener('change', updateNetworkInputStates);
      }
      if (networkFileInput) {
          networkFileInput.addEventListener('change', function() {
              displayNetworkFileNameCreate(this);
          });
      }

      const semanticToggle = document.getElementById('memory_semantic_enabled');
      if (semanticToggle) {
          semanticToggle.addEventListener('change', syncForumMemoryControls);
      }
    
      // Initial state
      updateNetworkInputStates();
      toggleForumMemorySettings();
      toggleForumMemoryAdvancedParams();
      syncForumMemoryControls();

      const archetypeToggle = document.getElementById('enable_archetypes');
      const archetypeDetails = document.getElementById('archetype-details');

      function updateArchetypeToggle() {
          if (!archetypeToggle || !archetypeDetails) return;

          if (archetypeToggle.checked) {
              archetypeDetails.style.opacity = '1';
              archetypeDetails.style.pointerEvents = 'auto';
          } else {
              archetypeDetails.style.opacity = '0.5';
              archetypeDetails.style.pointerEvents = 'none';
              archetypeDetails.open = false;
          }
      }

      if (archetypeToggle) {
          archetypeToggle.addEventListener('change', updateArchetypeToggle);
          updateArchetypeToggle();
      }

      toggleSimulationAdvancedParams();
  });
})();
