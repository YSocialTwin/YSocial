(function() {
    // Tutorial state
    let currentStep = 1;
    let tutorialData = null;
    let selectedEducation = [];
    let selectedPolitical = [];
    let createdExperimentId = null;
    let createdClientId = null;
    let llmEnabled = false;
    let topicsList = [];
    let tutAssignedProfiles = [];  // Activity profiles assigned with percentages
    
    // Check if tutorial should be shown
    function checkTutorialStatus() {
        fetch('/admin/tutorial/check_status')
            .then(response => response.json())
            .then(data => {
                if (data.show_tutorial && (data.role === 'admin' || data.role === 'researcher')) {
                    loadTutorialData();
                }
            })
            .catch(error => console.error('Error checking tutorial status:', error));
    }
    
    // Load tutorial form data
    function loadTutorialData() {
        fetch('/admin/tutorial/data')
            .then(response => response.json())
            .then(data => {
                tutorialData = data;
                populateFormOptions();
                setupLLMToggle();
                setupTopicsInput();
                setupNumberScales();
                setupActivityProfileDragDrop();
                showTutorial();
            })
            .catch(error => console.error('Error loading tutorial data:', error));
    }
    
    // Populate form options from API data
    function populateFormOptions() {
        // Education levels - multi-select dropdown
        const educationDropdown = document.getElementById('tut-education-dropdown');
        educationDropdown.innerHTML = tutorialData.education_levels.map(e => 
            `<div class="multi-select-option" data-id="${e.id}" data-name="${e.name}" onclick="toggleTutOption('education', '${e.name}', ${e.id})" style="padding: 8px 12px; cursor: pointer; font-size: 0.9em; transition: background 0.15s;">${e.name}</div>`
        ).join('');
        
        // Political leanings - multi-select dropdown
        const politicalDropdown = document.getElementById('tut-political-dropdown');
        politicalDropdown.innerHTML = tutorialData.political_leanings.map(p => 
            `<div class="multi-select-option" data-id="${p.id}" data-name="${p.name}" onclick="toggleTutOption('political', '${p.name}', ${p.id})" style="padding: 8px 12px; cursor: pointer; font-size: 0.9em; transition: background 0.15s;">${p.name}</div>`
        ).join('');
        
        // Activity profiles - now rendered as draggable items
        renderTutAvailableProfiles();
        
        // Set default activity profile ("Always On" at 100%)
        const alwaysOnProfile = tutorialData.activity_profiles.find(p => p.name === 'Always On');
        if (alwaysOnProfile) {
            tutAssignedProfiles = [{
                id: alwaysOnProfile.id,
                name: alwaysOnProfile.name,
                hours: alwaysOnProfile.hours || '',
                percentage: 100
            }];
            renderTutAssignedProfiles();
            validateTutActivityPercentages();
        }
        
        // Content recommendation systems - use 'name' as value (class name) and 'value' as display text
        const contentSelect = document.getElementById('tut-content-recsys');
        contentSelect.innerHTML = tutorialData.content_recsys.map(c => 
            `<option value="${c.name}">${c.value}</option>`
        ).join('');
        
        // Follow recommendation systems - use 'name' as value (class name) and 'value' as display text
        const followSelect = document.getElementById('tut-follow-recsys');
        followSelect.innerHTML = tutorialData.follow_recsys.map(f => 
            `<option value="${f.name}">${f.value}</option>`
        ).join('');
        
        // LLM models (if available)
        const llmModelSelect = document.getElementById('tut-llm-model');
        if (tutorialData.ollama_models && tutorialData.ollama_models.length > 0) {
            llmModelSelect.innerHTML = tutorialData.ollama_models.map(m => 
                `<option value="${m}">${m}</option>`
            ).join('');
        }
        
        // Update LLM section based on Ollama availability
        updateLLMAvailability();
    }
    
    // Render available activity profiles
    function renderTutAvailableProfiles() {
        const container = document.getElementById('tut-available-profiles');
        if (!container || !tutorialData.activity_profiles) return;
        
        // Filter out already assigned profiles
        const available = tutorialData.activity_profiles.filter(p => 
            !tutAssignedProfiles.find(ap => ap.id === p.id)
        );
        
        if (available.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: #999; font-size: 0.8em; padding: 8px;">All profiles assigned</div>';
            return;
        }
        
        container.innerHTML = available.map(p => {
            const hours = p.hours ? p.hours.split(',') : [];
            return `
            <div class="tut-profile-item" draggable="true" data-profile-id="${p.id}" data-profile-name="${p.name}" data-profile-hours="${p.hours || ''}" style="
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 8px;
                cursor: move;
                transition: all 0.2s ease;
                font-size: 0.8em;
            ">
                <div style="font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${p.name}">${p.name}</div>
                <div style="display: flex; gap: 1px; height: 8px; margin-top: 4px;">
                    ${Array.from({length: 24}, (_, h) => `<div style="flex: 1; height: 100%; background: ${hours.includes(h.toString()) ? '#22c55e' : '#e5e7eb'}; border-radius: 1px;" title="Hour ${h}"></div>`).join('')}
                </div>
            </div>
        `}).join('');
        
        // Add drag event listeners
        container.querySelectorAll('.tut-profile-item').forEach(item => {
            item.addEventListener('dragstart', handleTutProfileDragStart);
            item.addEventListener('dragend', handleTutProfileDragEnd);
        });
    }
    
    // Render assigned activity profiles
    function renderTutAssignedProfiles() {
        const container = document.getElementById('tut-assigned-profiles');
        if (!container) return;
        
        if (tutAssignedProfiles.length === 0) {
            container.innerHTML = '<div class="empty-state" style="text-align: center; color: #999; font-size: 0.8em; padding: 10px;">Drag profiles here to assign them</div>';
            return;
        }
        
        container.innerHTML = '<div style="display: flex; flex-wrap: wrap; gap: 8px;">' + tutAssignedProfiles.map(profile => `
            <div class="tut-assigned-profile" style="
                background: white;
                border: 1px solid #22c55e;
                border-radius: 4px;
                padding: 6px 8px;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: 0.8em;
            ">
                <span style="font-weight: 500; color: #333;">${profile.name}</span>
                <input type="number" 
                       class="tut-percentage-input" 
                       min="0" 
                       max="100" 
                       step="0.01"
                       placeholder="%" 
                       value="${profile.percentage || ''}"
                       onchange="updateTutProfilePercentage('${profile.id}', this.value)"
                       style="width: 55px; padding: 3px 5px; border: 1px solid #ddd; border-radius: 3px; text-align: center; font-size: 0.85em;">
                <span style="font-size: 0.75em; color: #666;">%</span>
                <button type="button" onclick="removeTutProfile('${profile.id}')" style="
                    background: #dc3545;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 3px 6px;
                    cursor: pointer;
                    font-size: 0.75em;
                ">×</button>
            </div>
        `).join('') + '</div>';
        
        // Re-render available to exclude assigned
        renderTutAvailableProfiles();
    }
    
    // Setup activity profile drag and drop
    function setupActivityProfileDragDrop() {
        const assignedContainer = document.getElementById('tut-assigned-profiles');
        if (assignedContainer) {
            assignedContainer.addEventListener('dragover', handleTutProfileDragOver);
            assignedContainer.addEventListener('drop', handleTutProfileDrop);
            assignedContainer.addEventListener('dragleave', handleTutProfileDragLeave);
        }
    }
    
    function handleTutProfileDragStart(e) {
        e.currentTarget.style.opacity = '0.5';
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('text/plain', JSON.stringify({
            id: e.currentTarget.dataset.profileId,
            name: e.currentTarget.dataset.profileName,
            hours: e.currentTarget.dataset.profileHours
        }));
    }
    
    function handleTutProfileDragEnd(e) {
        e.currentTarget.style.opacity = '1';
    }
    
    function handleTutProfileDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        e.currentTarget.style.backgroundColor = '#dcfce7';
        e.currentTarget.style.borderColor = '#22c55e';
    }
    
    function handleTutProfileDragLeave(e) {
        if (e.currentTarget === e.target) {
            e.currentTarget.style.backgroundColor = '#f0fdf4';
            e.currentTarget.style.borderColor = '';
        }
    }
    
    function handleTutProfileDrop(e) {
        e.preventDefault();
        e.currentTarget.style.backgroundColor = '#f0fdf4';
        e.currentTarget.style.borderColor = '';
        
        const data = JSON.parse(e.dataTransfer.getData('text/plain'));
        
        // Check if profile is already assigned
        if (tutAssignedProfiles.find(p => p.id === data.id)) {
            return;
        }
        
        // Add to assigned profiles
        tutAssignedProfiles.push({
            id: data.id,
            name: data.name,
            hours: data.hours,
            percentage: 0
        });
        
        renderTutAssignedProfiles();
        validateTutActivityPercentages();
    }
    
    // Update profile percentage
    window.updateTutProfilePercentage = function(profileId, value) {
        const profile = tutAssignedProfiles.find(p => p.id === profileId);
        if (profile) {
            profile.percentage = parseFloat(value) || 0;
            validateTutActivityPercentages();
        }
    };
    
    // Remove assigned profile
    window.removeTutProfile = function(profileId) {
        tutAssignedProfiles = tutAssignedProfiles.filter(p => p.id !== profileId);
        renderTutAssignedProfiles();
        validateTutActivityPercentages();
    };
    
    // Validate activity profile percentages
    function validateTutActivityPercentages() {
        const validation = document.getElementById('tut-activity-validation');
        if (!validation) return true;
        
        const total = tutAssignedProfiles.reduce((sum, p) => sum + (p.percentage || 0), 0);
        
        if (tutAssignedProfiles.length === 0) {
            validation.style.display = 'none';
            return true;
        }
        
        validation.style.display = 'block';
        
        if (Math.abs(total - 100) < 0.01) {
            validation.style.background = '#efe';
            validation.style.border = '1px solid #cfc';
            validation.style.color = '#0a0';
            validation.textContent = `✓ Total: ${total.toFixed(2)}% - Perfect!`;
            return true;
        } else {
            validation.style.background = '#fee';
            validation.style.border = '1px solid #fcc';
            validation.style.color = '#c00';
            validation.textContent = `⚠ Total: ${total.toFixed(2)}% - Must equal 100%`;
            return false;
        }
    }
    
    // Toggle multi-select dropdown visibility
    window.toggleTutDropdown = function(type) {
        const dropdown = document.getElementById(`tut-${type}-dropdown`);
        const isActive = dropdown.style.display === 'block';
        
        // Close all dropdowns first
        document.querySelectorAll('.multi-select-dropdown').forEach(d => d.style.display = 'none');
        
        // Toggle the clicked one
        if (!isActive) {
            dropdown.style.display = 'block';
        }
    };
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.multi-select-wrapper')) {
            document.querySelectorAll('.multi-select-dropdown').forEach(d => d.style.display = 'none');
        }
    });
    
    // Toggle option selection in multi-select
    window.toggleTutOption = function(type, name, id) {
        let array = type === 'education' ? selectedEducation : selectedPolitical;
        const option = document.querySelector(`#tut-${type}-dropdown .multi-select-option[data-id="${id}"]`);
        
        const existingIndex = array.findIndex(item => item.id === id);
        if (existingIndex > -1) {
            // Remove
            array.splice(existingIndex, 1);
            option.style.background = '';
            option.style.color = '';
            option.style.fontWeight = '';
        } else {
            // Add
            array.push({ id: id, name: name });
            option.style.background = '#e8f5e9';
            option.style.color = '#22c55e';
            option.style.fontWeight = '500';
        }
        
        updateTutMultiSelectDisplay(type);
    };
    
    // Update the display of selected items
    function updateTutMultiSelectDisplay(type) {
        const array = type === 'education' ? selectedEducation : selectedPolitical;
        const display = document.getElementById(`tut-${type}-display`);
        const wrapper = document.getElementById(`tut-${type}-display-wrapper`);
        
        if (array.length === 0) {
            wrapper.innerHTML = `<span id="tut-${type}-display" class="multi-select-placeholder" style="color: #999; font-size: 0.9em;">Click to select ${type === 'education' ? 'education levels' : 'political leanings'}...</span>`;
        } else {
            wrapper.innerHTML = array.map(item => 
                `<span class="multi-select-tag" style="background: #22c55e; color: white; padding: 3px 8px; border-radius: 3px; font-size: 0.85em; display: inline-flex; align-items: center; gap: 5px;">
                    ${item.name}
                    <span class="multi-select-tag-remove" onclick="event.stopPropagation(); toggleTutOption('${type}', '${item.name}', ${item.id})" style="cursor: pointer; font-weight: bold;">×</span>
                </span>`
            ).join('');
        }
    }
    
    // Setup number scale interactions
    function setupNumberScales() {
        const scales = ['tut-post-scale', 'tut-comment-scale', 'tut-read-scale'];
        
        scales.forEach(scaleId => {
            const scale = document.getElementById(scaleId);
            if (!scale) return;
            
            const boxes = scale.querySelectorAll('.number-box');
            const hiddenInput = scale.parentElement.querySelector('input[type="hidden"]');
            
            boxes.forEach(box => {
                box.addEventListener('click', function() {
                    // Remove selected from all boxes in this scale
                    boxes.forEach(b => {
                        b.classList.remove('selected');
                        b.style.backgroundColor = '';
                        b.style.color = '';
                        b.style.borderColor = '#ccc';
                    });
                    
                    // Add selected to clicked box
                    this.classList.add('selected');
                    this.style.backgroundColor = '#C1E0E6';
                    this.style.color = '#888';
                    this.style.borderColor = '#888';
                    
                    // Update hidden input
                    if (hiddenInput) {
                        hiddenInput.value = this.dataset.value;
                    }
                });
                
                // Hover effects
                box.addEventListener('mouseenter', function() {
                    if (!this.classList.contains('selected')) {
                        this.style.borderColor = '#888';
                    }
                });
                
                box.addEventListener('mouseleave', function() {
                    if (!this.classList.contains('selected')) {
                        this.style.borderColor = '#ccc';
                    }
                });
            });
        });
    }
    
    // Setup LLM toggle behavior
    function setupLLMToggle() {
        const toggle = document.getElementById('tut-llm-toggle');
        const slider = toggle.nextElementSibling;
        
        // Style the slider
        slider.innerHTML = '<span style="position: absolute; left: 3px; top: 3px; width: 16px; height: 16px; background: white; border-radius: 50%; transition: 0.4s;"></span>';
        
        toggle.addEventListener('change', function() {
            llmEnabled = this.checked;
            updateLLMUI();
        });
    }
    
    // Update LLM availability UI
    function updateLLMAvailability() {
        const toggle = document.getElementById('tut-llm-toggle');
        const section = document.getElementById('tut-llm-section');
        const icon = document.getElementById('tut-llm-icon');
        const status = document.getElementById('tut-llm-status');
        const desc = document.getElementById('tut-llm-desc');
        
        if (!tutorialData.ollama_available) {
            // Ollama not available - disable toggle
            toggle.disabled = true;
            section.style.borderLeftColor = '#ccc';
            icon.className = 'mdi mdi-robot-off';
            icon.style.color = '#ccc';
            status.textContent = 'Unavailable';
            status.style.background = '#ccc';
            desc.textContent = 'Ollama is not running. Start Ollama to enable LLM agents.';
        } else {
            // Ollama available - enable toggle
            toggle.disabled = false;
            section.style.borderLeftColor = '#039be5';
        }
    }
    
    // Update LLM-related UI elements
    function updateLLMUI() {
        const toggle = document.getElementById('tut-llm-toggle');
        const slider = toggle.nextElementSibling;
        const icon = document.getElementById('tut-llm-icon');
        const status = document.getElementById('tut-llm-status');
        const section = document.getElementById('tut-llm-section');
        const topicsSection = document.getElementById('tut-topics-section');
        const llmModelSection = document.getElementById('tut-llm-model-section');
        const knob = slider.querySelector('span');
        
        if (llmEnabled) {
            knob.style.transform = 'translateX(18px)';
            slider.style.backgroundColor = '#22c55e';
            icon.className = 'mdi mdi-robot';
            icon.style.color = '#22c55e';
            status.textContent = 'Enabled';
            status.style.background = '#22c55e';
            section.style.borderLeftColor = '#22c55e';
            topicsSection.style.display = 'block';
            llmModelSection.style.display = 'block';
        } else {
            knob.style.transform = 'translateX(0)';
            slider.style.backgroundColor = '#ccc';
            icon.className = 'mdi mdi-robot-off';
            icon.style.color = '#6c757d';
            status.textContent = 'Disabled';
            status.style.background = '#6c757d';
            section.style.borderLeftColor = '#039be5';
            topicsSection.style.display = 'none';
            llmModelSection.style.display = 'none';
        }
    }
    
    // Setup topics input
    function setupTopicsInput() {
        const input = document.getElementById('tut-topic-input');
        const container = document.getElementById('tut-topics-tags');
        
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const topic = this.value.trim();
                if (topic && !topicsList.includes(topic)) {
                    topicsList.push(topic);
                    renderTopicTags();
                    this.value = '';
                }
            }
        });
    }
    
    // Render topic tags
    function renderTopicTags() {
        const container = document.getElementById('tut-topics-tags');
        container.innerHTML = topicsList.map((topic, index) => `
            <span style="
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background: #039be5;
                color: white;
                padding: 4px 10px;
                border-radius: 15px;
                font-size: 0.85em;
            ">
                ${topic}
                <span onclick="removeTopic(${index})" style="
                    cursor: pointer;
                    font-size: 1.1em;
                    opacity: 0.8;
                    margin-left: 2px;
                ">&times;</span>
            </span>
        `).join('');
    }
    
    // Remove topic
    window.removeTopic = function(index) {
        topicsList.splice(index, 1);
        renderTopicTags();
    };
    
    // Show the tutorial overlay
    function showTutorial() {
        document.getElementById('tutorial-overlay').style.display = 'block';
        currentStep = 1;
        updateStepDisplay();
    }
    
    // Hide the tutorial overlay
    function hideTutorial() {
        document.getElementById('tutorial-overlay').style.display = 'none';
    }
    
    // Update step display
    function updateStepDisplay() {
        // Hide all steps
        document.querySelectorAll('.tutorial-step').forEach(el => el.style.display = 'none');
        
        // Show current step
        document.getElementById(`tutorial-step-${currentStep}`).style.display = 'block';
        
        // Update indicators
        for (let i = 1; i <= 4; i++) {
            const indicator = document.getElementById(`step-indicator-${i}`);
            if (i < currentStep) {
                indicator.style.background = '#22c55e';
                indicator.style.color = 'white';
                indicator.style.border = 'none';
            } else if (i === currentStep) {
                indicator.style.background = '#039be5';
                indicator.style.color = 'white';
                indicator.style.border = 'none';
            } else {
                indicator.style.background = '#f5f5f5';
                indicator.style.color = '#999';
                indicator.style.border = '1px solid #e6e6e6';
            }
        }
        
        // Update buttons
        const prevBtn = document.getElementById('tutorial-prev-btn');
        const nextBtn = document.getElementById('tutorial-next-btn');
        const skipBtn = document.getElementById('tutorial-skip-btn');
        
        // Hide prev button on step 4 (congratulations)
        prevBtn.style.display = (currentStep > 1 && currentStep < 4) ? 'block' : 'none';
        
        // Hide skip button on step 4
        skipBtn.style.display = currentStep < 4 ? 'block' : 'none';
        
        if (currentStep === 3) {
            nextBtn.innerHTML = 'Create Simulation <i class="mdi mdi-check"></i>';
        } else if (currentStep === 4) {
            nextBtn.innerHTML = '<i class="mdi mdi-play"></i> Run Simulation';
            nextBtn.style.background = 'linear-gradient(90deg, #22c55e 0%, #4ade80 100%)';
            nextBtn.style.boxShadow = '0 2px 6px rgba(34, 197, 94, 0.3)';
        } else {
            nextBtn.innerHTML = 'Next <i class="mdi mdi-arrow-right"></i>';
            nextBtn.style.background = 'linear-gradient(90deg, #039be5 0%, #4facfe 100%)';
            nextBtn.style.boxShadow = '0 2px 6px rgba(3, 155, 229, 0.3)';
        }
        
        // Clear error
        hideError();
    }
    
    // Show error message
    function showError(message) {
        const errorEl = document.getElementById('tutorial-error');
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
    
    // Hide error message
    function hideError() {
        document.getElementById('tutorial-error').style.display = 'none';
    }
    
    // Validate current step
    function validateStep() {
        hideError();
        
        if (currentStep === 1) {
            const name = document.getElementById('tut-pop-name').value.trim();
            if (!name) {
                showError('Please enter a population name.');
                return false;
            }
            if (selectedEducation.length === 0) {
                showError('Please select at least one education level.');
                return false;
            }
            if (selectedPolitical.length === 0) {
                showError('Please select at least one political leaning.');
                return false;
            }
            // Validate activity profiles
            if (tutAssignedProfiles.length === 0) {
                showError('Please assign at least one activity profile.');
                return false;
            }
            if (!validateTutActivityPercentages()) {
                showError('Activity profile percentages must sum to 100%.');
                return false;
            }
        } else if (currentStep === 2) {
            const name = document.getElementById('tut-exp-name').value.trim();
            if (!name) {
                showError('Please enter an experiment name.');
                return false;
            }
            // If LLM is enabled, require at least 2 topics
            if (llmEnabled && topicsList.length < 2) {
                showError('Please enter at least 2 topics for LLM agents.');
                return false;
            }
        } else if (currentStep === 3) {
            const name = document.getElementById('tut-client-name').value.trim();
            if (!name) {
                showError('Please enter a client name.');
                return false;
            }
            // If LLM is enabled, require a model selection
            if (llmEnabled) {
                const model = document.getElementById('tut-llm-model').value;
                if (!model) {
                    showError('Please select an LLM model.');
                    return false;
                }
            }
        }
        
        return true;
    }
    
    // Handle next button click
    function handleNext() {
        if (!validateStep()) return;
        
        if (currentStep < 3) {
            currentStep++;
            updateStepDisplay();
        } else if (currentStep === 3) {
            // Submit the form to create experiment
            createExperiment();
        } else if (currentStep === 4) {
            // Run the simulation
            runSimulation();
        }
    }
    
    // Handle previous button click
    function handlePrev() {
        if (currentStep > 1 && currentStep < 4) {
            currentStep--;
            updateStepDisplay();
        }
    }
    
    // Create the experiment
    function createExperiment() {
        const nextBtn = document.getElementById('tutorial-next-btn');
        nextBtn.disabled = true;
        nextBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Creating...';
        
        // Get the action relevance values (0-10 scale, convert to probability 0-1)
        const postValue = parseInt(document.getElementById('tut-post-prob').value);
        const commentValue = parseInt(document.getElementById('tut-comment-prob').value);
        const readValue = parseInt(document.getElementById('tut-read-prob').value);
        const shareValue = parseInt(document.getElementById('tut-share-prob').value);
        
        // Normalize to probabilities (sum should be 1 for meaningful distribution)
        const total = postValue + commentValue + readValue + shareValue;
        const postProb = total > 0 ? postValue / total : 0.25;
        const commentProb = total > 0 ? commentValue / total : 0.25;
        const readProb = total > 0 ? readValue / total : 0.25;
        const shareProb = total > 0 ? shareValue / total : 0.25;
        
        // Prepare activity profiles data (id -> percentage)
        const activityProfilesData = tutAssignedProfiles.map(p => ({
            id: p.id,
            name: p.name,
            percentage: p.percentage || 0
        }));
        
        const data = {
            // Population - extract just the IDs from the objects
            population_name: document.getElementById('tut-pop-name').value.trim(),
            population_size: parseInt(document.getElementById('tut-pop-size').value),
            education_levels: selectedEducation.map(e => e.id),
            political_leanings: selectedPolitical.map(p => p.id),
            activity_profiles_data: activityProfilesData,
            
            // Experiment
            experiment_name: document.getElementById('tut-exp-name').value.trim(),
            llm_enabled: llmEnabled,
            topics: topicsList,
            
            // Client
            client_name: document.getElementById('tut-client-name').value.trim(),
            simulation_days: parseInt(document.getElementById('tut-sim-days').value),
            post_probability: postProb,
            share_probability: shareProb,
            comment_probability: commentProb,
            read_probability: readProb,
            content_recsys: document.getElementById('tut-content-recsys').value,
            follow_recsys: document.getElementById('tut-follow-recsys').value,
            llm_model: llmEnabled ? document.getElementById('tut-llm-model').value : '',
        };
        
        fetch('/admin/tutorial/create_all', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                // Store the created IDs for later use
                createdExperimentId = result.experiment_id;
                createdClientId = result.client_id;
                
                // Move to congratulations step
                currentStep = 4;
                updateStepDisplay();
                
                // Re-enable the button
                const nextBtn = document.getElementById('tutorial-next-btn');
                nextBtn.disabled = false;
            } else {
                showError(result.message || 'An error occurred. Please try again.');
                nextBtn.disabled = false;
                nextBtn.innerHTML = 'Create Simulation <i class="mdi mdi-check"></i>';
            }
        })
        .catch(error => {
            console.error('Error creating experiment:', error);
            showError('An error occurred. Please try again.');
            nextBtn.disabled = false;
            nextBtn.innerHTML = 'Create Simulation <i class="mdi mdi-check"></i>';
        });
    }
    
    // Run the simulation (start server and client)
    function runSimulation() {
        const nextBtn = document.getElementById('tutorial-next-btn');
        nextBtn.disabled = true;
        nextBtn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Starting...';
        
        // Use the new JSON API endpoint to start both server and client
        fetch('/admin/tutorial/run_simulation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                experiment_id: createdExperimentId,
                client_id: createdClientId
            }),
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                // Redirect to experiment details page with from_tutorial param
                window.location.href = `/admin/experiment_details/${createdExperimentId}?from_tutorial=true`;
            } else {
                console.error('Error starting simulation:', result.message);
                // Still redirect - user can start manually
                window.location.href = `/admin/experiment_details/${createdExperimentId}?from_tutorial=true`;
            }
        })
        .catch(error => {
            console.error('Error starting simulation:', error);
            // Still redirect even if there's an error - the user can start manually
            window.location.href = `/admin/experiment_details/${createdExperimentId}?from_tutorial=true`;
        });
    }
    
    // Dismiss tutorial
    function dismissTutorial() {
        fetch('/admin/tutorial/dismiss', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(() => {
            hideTutorial();
        })
        .catch(error => {
            console.error('Error dismissing tutorial:', error);
            hideTutorial();
        });
    }
    
    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        // Check tutorial status on page load
        checkTutorialStatus();
        
        // Event listeners
        const nextBtn = document.getElementById('tutorial-next-btn');
        const prevBtn = document.getElementById('tutorial-prev-btn');
        const skipBtn = document.getElementById('tutorial-skip-btn');
        const closeBtn = document.getElementById('tutorial-close-btn');
        if (nextBtn) nextBtn.addEventListener('click', handleNext);
        if (prevBtn) prevBtn.addEventListener('click', handlePrev);
        if (skipBtn) skipBtn.addEventListener('click', dismissTutorial);
        if (closeBtn) closeBtn.addEventListener('click', dismissTutorial);
    });
    
    // Expose function to manually show tutorial (for "Show Tutorial" button)
    window.showTutorialWizard = function() {
        if (tutorialData) {
            // Reset selections
            selectedEducation = [];
            selectedPolitical = [];
            createdExperimentId = null;
            createdClientId = null;
            llmEnabled = false;
            topicsList = [];
            
            // Reset activity profiles to default ("Always On" at 100%)
            tutAssignedProfiles = [];
            const alwaysOnProfile = tutorialData.activity_profiles.find(p => p.name === 'Always On');
            if (alwaysOnProfile) {
                tutAssignedProfiles = [{
                    id: alwaysOnProfile.id,
                    name: alwaysOnProfile.name,
                    hours: alwaysOnProfile.hours || '',
                    percentage: 100
                }];
            }
            renderTutAssignedProfiles();
            validateTutActivityPercentages();
            
            // Reset multi-select displays
            updateTutMultiSelectDisplay('education');
            updateTutMultiSelectDisplay('political');
            
            // Reset multi-select dropdown options styling
            document.querySelectorAll('.multi-select-option').forEach(el => {
                el.style.background = '';
                el.style.color = '';
                el.style.fontWeight = '';
            });
            
            // Reset form inputs
            document.getElementById('tut-pop-name').value = '';
            document.getElementById('tut-pop-size').value = 50;
            document.getElementById('tut-pop-size-value').textContent = '50';
            document.getElementById('tut-exp-name').value = '';
            document.getElementById('tut-client-name').value = '';
            document.getElementById('tut-sim-days').value = 7;
            
            // Reset number scales to default values
            resetNumberScale('tut-post-scale', 3);
            resetNumberScale('tut-comment-scale', 5);
            resetNumberScale('tut-read-scale', 2);
            // Note: share-prob is kept at 0 via hidden input
            
            // Reset LLM toggle
            document.getElementById('tut-llm-toggle').checked = false;
            updateLLMUI();
            
            // Reset topics
            document.getElementById('tut-topics-tags').innerHTML = '';
            document.getElementById('tut-topic-input').value = '';
            
            // Reset button styles
            const nextBtn = document.getElementById('tutorial-next-btn');
            nextBtn.style.background = 'linear-gradient(135deg, #039be5 0%, #00bcd4 100%)';
            nextBtn.style.boxShadow = '0 4px 12px rgba(3, 155, 229, 0.3)';
            
            currentStep = 1;
            showTutorial();
        } else {
            loadTutorialData();
        }
    };
    
    // Helper function to reset number scale to a specific value
    function resetNumberScale(scaleId, value) {
        const scale = document.getElementById(scaleId);
        if (!scale) return;
        
        const boxes = scale.querySelectorAll('.number-box');
        const hiddenInput = scale.parentElement.querySelector('input[type="hidden"]');
        
        boxes.forEach(box => {
            const boxValue = parseInt(box.dataset.value);
            if (boxValue === value) {
                box.classList.add('selected');
                box.style.backgroundColor = '#C1E0E6';
                box.style.color = '#888';
                box.style.borderColor = '#888';
            } else {
                box.classList.remove('selected');
                box.style.backgroundColor = '';
                box.style.color = '';
                box.style.borderColor = '#ccc';
            }
        });
        
        if (hiddenInput) {
            hiddenInput.value = value;
        }
    }
})();
