(function() {
    // Tutorial configuration
    const tutorialSteps = [
        {
            id: 'server-controls',
            selector: '#server-controls-section',
            title: '🖥️ Server & Analysis Controls',
            description: `<p>This is your <b>command center</b> for managing the experiment server and analysis tools:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Start/Stop Server</b> - Launch or terminate the experiment server</li>
                    <li><b>Load Experiment</b> - Make this experiment's web interface accessible</li>
                    <li><b>JupyterLab</b> - Start the analysis environment for exploring data</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'simulation-clients',
            selector: '#simulation-clients-section',
            title: '🤖 Simulation Clients',
            description: `<p>Here you manage the <b>simulation clients</b> that run your agent populations:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Progress Bar</b> - Shows real-time simulation progress</li>
                    <li><b>Play/Pause</b> - Start or pause individual clients</li>
                    <li><b>Add Client</b> - Create new simulation configurations</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Each client can run different agent behaviors and parameters.</p>`,
            position: 'right'
        },
        {
            id: 'actions',
            selector: '#actions-section',
            title: '⚡ Actions',
            description: `<p>Quick actions to manage your experiment:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Edit LLM Prompts</b> - Customize agent behavior instructions</li>
                    <li><b>Download Experiment</b> - Export all data and configuration</li>
                    <li><b>Delete Experiment</b> - Remove the experiment (use with caution!)</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'server-trends',
            selector: '#server-trends-section',
            title: '📈 Server Trends Analysis',
            description: `<p>Monitor your simulation's <b>performance over time</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Server Compute Time</b> - Track server processing load</li>
                    <li><b>Client Compute Time</b> - Monitor client-side performance</li>
                    <li><b>Simulation Time Trend</b> - See how long each simulated day takes</li>
                    <li><b>Remaining Time Forecast</b> - Estimate when simulation will complete</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Switch between daily/hourly views for different granularity.</p>`,
            position: 'overlay'
        },
        {
            id: 'server-logs',
            selector: '#server-logs-section',
            title: '📊 Server Logs Analysis',
            description: `<p>Analyze <b>API call patterns</b> from the server:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Call Volume by Path</b> - See which endpoints are most used</li>
                    <li><b>Mean Duration by Path</b> - Identify slow operations</li>
                    <li><b>Path Filters</b> - Focus on specific API endpoints</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Use auto-refresh to monitor in real-time.</p>`,
            position: 'overlay'
        },
        {
            id: 'client-logs',
            selector: '#client-logs-section',
            title: '📉 Client Logs Analysis',
            description: `<p>Examine <b>client execution patterns</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Select a Client</b> - Choose which client to analyze</li>
                    <li><b>Call Volume by Method</b> - See agent action distribution</li>
                    <li><b>Mean Execution Time</b> - Track action performance</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Great for understanding agent behavior patterns.</p>`,
            position: 'overlay'
        },
        {
            id: 'load-experiment',
            selector: '#load-experiment-btn',
            title: '🔄 Load Experiment Interface',
            description: `<p>The <b>Load Experiment</b> button activates the web interface for this experiment.</p>
                <p style="margin-top: 10px;">Once loaded, you can:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Navigate the social network as a human participant</li>
                    <li>View agent posts and interactions</li>
                    <li>Join the simulation alongside synthetic agents</li>
                </ul>
                <p style="margin-top: 12px; padding: 10px; background: #e8f5e9; border-radius: 6px; font-size: 0.9em;">
                    <b>💡 Try it now!</b> Click the button to load this experiment's interface, then use the <i class="mdi mdi-login"></i> button to join.
                </p>`,
            position: 'right',
            forceVisible: true
        },
        {
            id: 'jupyter-controls',
            selector: '#jupyter-controls',
            title: '🔬 JupyterLab Analysis',
            description: `<p>The <b>JupyterLab</b> button launches an interactive analysis environment.</p>
                <p style="margin-top: 10px;">With JupyterLab, you can:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Run Python notebooks to analyze experiment data</li>
                    <li>Create custom visualizations and reports</li>
                    <li>Access the raw database and logs</li>
                </ul>
                <p style="margin-top: 12px; padding: 10px; background: #e3f2fd; border-radius: 6px; font-size: 0.9em;">
                    <b>💡 Tip:</b> Click the flask icon to start the JupyterLab server when you need advanced data analysis.
                </p>`,
            position: 'right',
            forceVisible: true,
            isLast: true
        }
    ];
    
    let currentStep = 0;
    let tutorialActive = false;
    
    // Check if tutorial should be shown
    function checkTutorialStatus() {
        // Check if we came from the onboarding wizard
        const urlParams = new URLSearchParams(window.location.search);
        const fromTutorial = urlParams.get('from_tutorial') === 'true';
        
        // If coming from onboarding tutorial, always show the exp details tutorial
        if (fromTutorial) {
            // Show tutorial after a short delay to let the page render
            setTimeout(() => {
                startTutorial();
            }, 1000);
            return;
        }
        
        // Otherwise, check the status from the server (only show if not seen before)
        fetch('/admin/tutorial/exp_details/check_status')
            .then(response => response.json())
            .then(data => {
                if (data.show_tutorial && (data.role === 'admin' || data.role === 'researcher')) {
                    // Show tutorial after a short delay to let the page render
                    setTimeout(() => {
                        startTutorial();
                    }, 1000);
                }
            })
            .catch(error => console.error('Error checking tutorial status:', error));
    }
    
    // Start the tutorial
    function startTutorial() {
        tutorialActive = true;
        currentStep = 0;
        document.getElementById('exp-details-tutorial-overlay').style.display = 'block';
        showStep(currentStep);
    }
    
    // Find element by selector
    function findElement(step) {
        if (step.selector) {
            try {
                return document.querySelector(step.selector);
            } catch (e) {
                console.warn('Invalid selector:', step.selector, e);
            }
        }
        return null;
    }
    
    // Track the currently highlighted element for cleanup
    let currentHighlightedElement = null;
    
    // Show a specific step
    function showStep(stepIndex) {
        const step = tutorialSteps[stepIndex];
        const element = findElement(step);
        
        if (!element) {
            console.warn('Element not found for step:', step.id);
            // Skip to next step if element not found (unless forceVisible is set)
            if (!step.forceVisible && stepIndex < tutorialSteps.length - 1) {
                currentStep++;
                showStep(currentStep);
            } else if (stepIndex < tutorialSteps.length - 1) {
                currentStep++;
                showStep(currentStep);
            } else {
                hideTutorial();
            }
            return;
        }
        
        // Update step indicator
        document.getElementById('exp-tutorial-step-indicator').textContent = 
            `Step ${stepIndex + 1} of ${tutorialSteps.length}`;
        
        // Update content
        document.getElementById('exp-tutorial-title').textContent = step.title;
        document.getElementById('exp-tutorial-description').innerHTML = step.description;
        
        // Update button text for last step
        const nextBtn = document.getElementById('exp-tutorial-next');
        if (step.isLast) {
            nextBtn.textContent = 'Finish Tutorial ✓';
            nextBtn.style.background = 'linear-gradient(135deg, #4caf50 0%, #66bb6a 100%)';
        } else {
            nextBtn.textContent = 'Got it! Next →';
            nextBtn.style.background = 'linear-gradient(135deg, #039be5 0%, #00bcd4 100%)';
        }
        
        // Remove highlight from previous element
        if (currentHighlightedElement) {
            currentHighlightedElement.style.position = '';
            currentHighlightedElement.style.zIndex = '';
            currentHighlightedElement.style.background = '';
            currentHighlightedElement.style.borderRadius = '';
            currentHighlightedElement.style.boxShadow = '';
        }
        
        // Add high z-index and white background to current element to bring it above the backdrop
        currentHighlightedElement = element;
        const originalPosition = window.getComputedStyle(element).position;
        if (originalPosition === 'static') {
            element.style.position = 'relative';
        }
        element.style.zIndex = '9998';
        
        // Add white background to ensure element is visible (not dimmed)
        const computedBg = window.getComputedStyle(element).backgroundColor;
        if (!computedBg || computedBg === 'transparent' || computedBg === 'rgba(0, 0, 0, 0)') {
            element.style.background = '#fff';
            element.style.borderRadius = '8px';
            element.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.15)';
        }
        
        // Scroll element into view first, then position elements after scroll completes
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // Wait for scroll to complete before positioning tooltip
        setTimeout(() => {
            positionElements(element, step.position);
            
            // Add pulse animation
            const highlight = document.getElementById('exp-tutorial-highlight');
            highlight.classList.add('pulse');
        }, 500);
    }
    
    // Position the highlight and tooltip
    function positionElements(element, position) {
        const highlight = document.getElementById('exp-tutorial-highlight');
        const tooltip = document.getElementById('exp-tutorial-tooltip');
        
        const rect = element.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
        
        // Position highlight
        const padding = 8;
        highlight.style.top = (rect.top + scrollTop - padding) + 'px';
        highlight.style.left = (rect.left + scrollLeft - padding) + 'px';
        highlight.style.width = (rect.width + padding * 2) + 'px';
        highlight.style.height = (rect.height + padding * 2) + 'px';
        
        // Get tooltip dimensions after content is set
        tooltip.style.visibility = 'hidden';
        tooltip.style.display = 'block';
        const tooltipRect = tooltip.getBoundingClientRect();
        tooltip.style.visibility = '';
        
        const gap = 15;
        const tooltipWidth = 400;
        const tooltipHeight = tooltipRect.height;
        
        let tooltipTop, tooltipLeft;
        
        switch (position) {
            case 'right':
                tooltipTop = rect.top + scrollTop;
                tooltipLeft = rect.right + scrollLeft + gap;
                // Check if tooltip goes off screen
                if (tooltipLeft + tooltipWidth > window.innerWidth) {
                    tooltipLeft = rect.left + scrollLeft - tooltipWidth - gap;
                }
                break;
            case 'left':
                tooltipTop = rect.top + scrollTop;
                tooltipLeft = rect.left + scrollLeft - tooltipWidth - gap;
                if (tooltipLeft < 0) {
                    tooltipLeft = rect.right + scrollLeft + gap;
                }
                break;
            case 'top':
                tooltipTop = rect.top + scrollTop - tooltipHeight - gap;
                tooltipLeft = rect.left + scrollLeft + (rect.width / 2) - (tooltipWidth / 2);
                if (tooltipTop < scrollTop) {
                    tooltipTop = rect.bottom + scrollTop + gap;
                }
                break;
            case 'overlay':
                // Position tooltip centered on top of the element
                tooltipTop = rect.top + scrollTop + (rect.height / 2) - (tooltipHeight / 2);
                tooltipLeft = rect.left + scrollLeft + (rect.width / 2) - (tooltipWidth / 2);
                break;
            case 'bottom':
            default:
                tooltipTop = rect.bottom + scrollTop + gap;
                // Center tooltip relative to the element, but ensure it stays visible
                tooltipLeft = rect.left + scrollLeft + (rect.width / 2) - (tooltipWidth / 2);
                break;
        }
        
        // Ensure tooltip stays on screen horizontally
        tooltipLeft = Math.max(10, Math.min(tooltipLeft, window.innerWidth - tooltipWidth - 10));
        // Ensure tooltip stays on screen vertically (use current viewport)
        const viewportTop = scrollTop;
        const viewportBottom = scrollTop + window.innerHeight;
        tooltipTop = Math.max(viewportTop + 10, Math.min(tooltipTop, viewportBottom - tooltipHeight - 10));
        
        tooltip.style.top = tooltipTop + 'px';
        tooltip.style.left = tooltipLeft + 'px';
    }
    
    // Go to next step
    function nextStep() {
        currentStep++;
        if (currentStep >= tutorialSteps.length) {
            hideTutorial();
        } else {
            showStep(currentStep);
        }
    }
    
    // Hide tutorial and mark as completed
    function hideTutorial() {
        tutorialActive = false;
        
        // Clean up highlighted element
        if (currentHighlightedElement) {
            currentHighlightedElement.style.position = '';
            currentHighlightedElement.style.zIndex = '';
            currentHighlightedElement.style.background = '';
            currentHighlightedElement.style.borderRadius = '';
            currentHighlightedElement.style.boxShadow = '';
            currentHighlightedElement = null;
        }
        
        document.getElementById('exp-details-tutorial-overlay').style.display = 'none';
        
        // Mark tutorial as completed
        fetch('/admin/tutorial/exp_details/dismiss', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        }).catch(error => console.error('Error dismissing tutorial:', error));
    }
    
    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        // Check tutorial status
        checkTutorialStatus();
        
        // Event listeners
        document.getElementById('exp-tutorial-next').addEventListener('click', nextStep);
        document.getElementById('exp-tutorial-skip').addEventListener('click', hideTutorial);
        document.getElementById('exp-tutorial-close').addEventListener('click', hideTutorial);
        
        // Handle window resize
        let resizeTimeout;
        window.addEventListener('resize', function() {
            if (tutorialActive) {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    showStep(currentStep);
                }, 200);
            }
        });
    });
    
    // Expose function to manually start tutorial
    window.startExpDetailsTutorial = function() {
        currentStep = 0;
        // Reset the tutorial flag first
        fetch('/admin/tutorial/exp_details/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        }).then(() => {
            startTutorial();
        }).catch(error => {
            console.error('Error resetting tutorial:', error);
            startTutorial();
        });
    };
})();
