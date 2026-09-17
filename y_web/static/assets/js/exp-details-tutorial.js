(function() {
    // Tutorial configuration
    const tutorialSteps = [
        // 1) General configuration
        {
            id: 'experiment-overview',
            selector: '#experiment-overview-section',
            title: '🧾 Experiment Overview',
            description: `<p>This left-side box is the main configuration area for the experiment.</p>
                <p style="margin-top: 8px;">From here you review metadata, edit topics, and update runtime feature toggles.</p>`,
            position: 'right'
        },
        {
            id: 'simulation-topics',
            selector: '#experiment-topics-tags',
            title: '🏷️ Simulation Topics',
            description: `<p>Topics define the thematic space for content and interaction.</p>
                <p style="margin-top: 8px;">Maintain this list before launching clients so their behavior is aligned with current experiment scope.</p>`,
            position: 'right'
        },
        {
            id: 'configuration-actions',
            selector: '#actions-section',
            title: '⚙️ Additional Configuration & Management',
            description: `<p>Use this panel to open prompts, embedding settings, stress/reward controls, and lifecycle actions (download/delete).</p>`,
            position: 'right'
        },
        // 2) Server controls
        {
            id: 'server-controls',
            selector: '#server-controls-section',
            title: '🖥️ Server Controls',
            description: `<p>This section controls experiment runtime services:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Start/stop server processes.</li>
                    <li>Load the experiment interface.</li>
                    <li>Start JupyterLab for analysis.</li>
                </ul>`,
            position: 'right'
        },
        // 3) Client creation and execution
        {
            id: 'simulation-clients',
            selector: '#simulation-clients-section',
            title: '🤖 Simulation Clients',
            description: `<p>Manage standard clients that execute simulation rounds:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Monitor progress bars and status.</li>
                    <li>Start, pause, or stop client runs.</li>
                    <li>Open client-specific configuration links.</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'adhoc-clients',
            selector: '#adhoc-agent-clients-section',
            title: '🧩 Ad Hoc Agent Clients',
            description: `<p>This section is dedicated to plugin-backed ad hoc clients.</p>
                <p style="margin-top: 8px;">Use it to run specialized agent families independently from the standard client set.</p>`,
            position: 'right'
        },
        // 4) Runtime analysis and trends
        {
            id: 'analytics-cards',
            selector: '.ys-analytics-page-card',
            title: '📚 Analytics Shortcuts',
            description: `<p>Use these cards to open dedicated analytics pages after runtime data starts accumulating.</p>`,
            position: 'left'
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
        // 5) Interface/evolution wrap-up
        {
            id: 'load-experiment',
            selector: '#load-experiment-btn',
            title: '🔄 Load Experiment Interface',
            description: `<p>This button activates the user-facing interface for the selected experiment.</p>
                <p style="margin-top: 10px;">After loading, you can inspect feeds, profiles, and live interaction behavior directly.</p>`,
            position: 'right',
            forceVisible: true
        },
        {
            id: 'quick-reference',
            selector: '#quick-reference-section',
            title: '📌 Quick Reference',
            description: `<p>This panel summarizes the recommended operational workflow: configure, run, inspect logs/trends, then analyze evolution pages.</p>`,
            position: 'left'
        },
        {
            id: 'evolution-pages',
            selector: '#analytics-pages-section',
            title: '📈 Experiment Evolution Pages',
            description: `<p>Finalize your analysis from the evolution dashboards (network, topic/hashtag, recsys, opinion, stress/reward, and annotation trends).</p>`,
            position: 'left',
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
        const overlay = document.getElementById('exp-details-tutorial-overlay');
        if (!overlay) return;
        overlay.classList.remove('d-none');
        overlay.style.display = 'block';
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
        
        const overlay = document.getElementById('exp-details-tutorial-overlay');
        if (overlay) {
            overlay.classList.add('d-none');
            overlay.style.display = 'none';
        }
        
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
        const nextBtn = document.getElementById('exp-tutorial-next');
        const skipBtn = document.getElementById('exp-tutorial-skip');
        const closeBtn = document.getElementById('exp-tutorial-close');
        if (nextBtn) nextBtn.addEventListener('click', nextStep);
        if (skipBtn) skipBtn.addEventListener('click', hideTutorial);
        if (closeBtn) closeBtn.addEventListener('click', hideTutorial);
        
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
