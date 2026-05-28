(function() {
    // Generic tutorial engine
    window.PageTutorialEngine = window.PageTutorialEngine || {};
    
    window.PageTutorialEngine.init = function(tutorialId, steps) {
        const overlay = document.getElementById(tutorialId + '-tutorial-overlay');
        if (!overlay) return null;
        
        const state = {
            id: tutorialId,
            steps: steps,
            currentStep: 0,
            active: false,
            currentHighlightedElement: null
        };
        
        const elements = {
            overlay: overlay,
            backdrop: overlay.querySelector('.tutorial-backdrop'),
            highlight: overlay.querySelector('.tutorial-highlight'),
            tooltip: overlay.querySelector('.tutorial-tooltip'),
            stepIndicator: overlay.querySelector('.tutorial-step-indicator'),
            title: overlay.querySelector('.tutorial-title'),
            description: overlay.querySelector('.tutorial-description'),
            nextBtn: overlay.querySelector('.tutorial-next'),
            skipBtn: overlay.querySelector('.tutorial-skip'),
            closeBtn: overlay.querySelector('.tutorial-close')
        };
        
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
        
        function positionElements(element, position) {
            const rect = element.getBoundingClientRect();
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
            const isMobile = window.innerWidth <= 768;
            
            // Position highlight - adjust padding for mobile
            const padding = isMobile ? 4 : 8;
            elements.highlight.style.top = (rect.top + scrollTop - padding) + 'px';
            elements.highlight.style.left = (rect.left + scrollLeft - padding) + 'px';
            elements.highlight.style.width = (rect.width + padding * 2) + 'px';
            elements.highlight.style.height = (rect.height + padding * 2) + 'px';
            
            // Get tooltip dimensions
            elements.tooltip.style.visibility = 'hidden';
            elements.tooltip.style.display = 'block';
            const tooltipRect = elements.tooltip.getBoundingClientRect();
            elements.tooltip.style.visibility = '';
            
            const gap = isMobile ? 10 : 15;
            // On mobile, use full width minus margins
            const tooltipWidth = isMobile ? (window.innerWidth - 20) : 400;
            const tooltipHeight = tooltipRect.height;
            
            let tooltipTop, tooltipLeft;
            
            // On mobile, always position tooltip at bottom or top of element
            if (isMobile) {
                // Check if there's more space above or below
                const spaceBelow = window.innerHeight - rect.bottom;
                const spaceAbove = rect.top;
                
                if (spaceBelow >= tooltipHeight + gap || spaceBelow > spaceAbove) {
                    // Position below
                    tooltipTop = rect.bottom + scrollTop + gap;
                } else {
                    // Position above
                    tooltipTop = rect.top + scrollTop - tooltipHeight - gap;
                }
                tooltipLeft = 10; // Always center on mobile
            } else {
                switch (position) {
                    case 'right':
                        tooltipTop = rect.top + scrollTop;
                        tooltipLeft = rect.right + scrollLeft + gap;
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
                        tooltipTop = rect.top + scrollTop + (rect.height / 2) - (tooltipHeight / 2);
                        tooltipLeft = rect.left + scrollLeft + (rect.width / 2) - (tooltipWidth / 2);
                        break;
                    case 'bottom':
                    default:
                        tooltipTop = rect.bottom + scrollTop + gap;
                        tooltipLeft = rect.left + scrollLeft + (rect.width / 2) - (tooltipWidth / 2);
                        break;
                }
            }
            
            // Ensure tooltip stays on screen
            const margin = isMobile ? 8 : 10;
            tooltipLeft = Math.max(margin, Math.min(tooltipLeft, window.innerWidth - tooltipWidth - margin));
            const viewportTop = scrollTop;
            const viewportBottom = scrollTop + window.innerHeight;
            tooltipTop = Math.max(viewportTop + margin, Math.min(tooltipTop, viewportBottom - tooltipHeight - margin));
            
            elements.tooltip.style.top = tooltipTop + 'px';
            elements.tooltip.style.left = tooltipLeft + 'px';
        }
        
        function showStep(stepIndex) {
            const step = state.steps[stepIndex];
            if (!step) return;
            
            const element = findElement(step);
            
            if (!element) {
                console.warn('Element not found for step:', step.id);
                if (stepIndex < state.steps.length - 1) {
                    state.currentStep++;
                    showStep(state.currentStep);
                } else {
                    hideTutorial();
                }
                return;
            }
            
            // Update UI
            elements.stepIndicator.textContent = `Step ${stepIndex + 1} of ${state.steps.length}`;
            elements.title.textContent = step.title;
            elements.description.innerHTML = step.description;
            
            // Update button
            if (step.isLast) {
                elements.nextBtn.textContent = 'Finish Tutorial ✓';
                elements.nextBtn.style.background = 'linear-gradient(135deg, #4caf50 0%, #66bb6a 100%)';
            } else {
                elements.nextBtn.textContent = 'Got it! Next →';
                elements.nextBtn.style.background = 'linear-gradient(135deg, #039be5 0%, #00bcd4 100%)';
            }
            
            // Clean up previous highlight
            if (state.currentHighlightedElement) {
                state.currentHighlightedElement.style.position = '';
                state.currentHighlightedElement.style.zIndex = '';
                state.currentHighlightedElement.style.background = '';
                state.currentHighlightedElement.style.borderRadius = '';
                state.currentHighlightedElement.style.padding = '';
                state.currentHighlightedElement.style.boxShadow = '';
                state.currentHighlightedElement.classList.remove('tutorial-highlighted');
            }
            
            // Highlight current element - elevate above backdrop with solid background
            state.currentHighlightedElement = element;
            const originalPosition = window.getComputedStyle(element).position;
            if (originalPosition === 'static') {
                element.style.position = 'relative';
            }
            
            // Check if element is inside sidebar
            const isInSidebar = element.closest('.dashboard-aside') !== null;
            
            if (isInSidebar) {
                // For sidebar elements, use CSS class for proper highlighting
                element.classList.add('tutorial-highlighted');
                // Also elevate the sidebar itself during tutorial
                const sidebar = element.closest('.dashboard-aside');
                if (sidebar) {
                    sidebar.style.zIndex = '9999';
                    sidebar.style.background = '#fff';
                }
            } else {
                // For other elements, apply inline styles
                element.style.zIndex = '9998';
                
                // Add white background so element appears above the dark backdrop
                const computedBg = window.getComputedStyle(element).backgroundColor;
                const isTransparent = !computedBg || computedBg === 'transparent' || computedBg === 'rgba(0, 0, 0, 0)';
                
                if (isTransparent) {
                    element.style.background = '#ffffff';
                    element.style.borderRadius = '8px';
                    element.style.padding = '10px 12px';
                    element.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
                }
            }
            
            // Scroll and position
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            setTimeout(() => {
                positionElements(element, step.position);
                elements.highlight.classList.add('pulse');
            }, 500);
        }
        
        function nextStep() {
            state.currentStep++;
            if (state.currentStep >= state.steps.length) {
                hideTutorial();
            } else {
                showStep(state.currentStep);
            }
        }
        
        function hideTutorial() {
            state.active = false;
            
            if (state.currentHighlightedElement) {
                state.currentHighlightedElement.style.position = '';
                state.currentHighlightedElement.style.zIndex = '';
                state.currentHighlightedElement.style.background = '';
                state.currentHighlightedElement.style.borderRadius = '';
                state.currentHighlightedElement.style.padding = '';
                state.currentHighlightedElement.style.boxShadow = '';
                state.currentHighlightedElement.classList.remove('tutorial-highlighted');
                
                // Reset sidebar z-index if element was in sidebar
                const sidebar = state.currentHighlightedElement.closest('.dashboard-aside');
                if (sidebar) {
                    sidebar.style.zIndex = '';
                }
                
                state.currentHighlightedElement = null;
            }
            
            elements.overlay.style.display = 'none';
        }
        
        function startTutorial() {
            state.active = true;
            state.currentStep = 0;
            elements.overlay.style.display = 'block';
            showStep(state.currentStep);
        }
        
        // Event listeners
        elements.nextBtn.addEventListener('click', nextStep);
        elements.skipBtn.addEventListener('click', hideTutorial);
        elements.closeBtn.addEventListener('click', hideTutorial);
        
        // Handle resize
        let resizeTimeout;
        window.addEventListener('resize', function() {
            if (state.active) {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    showStep(state.currentStep);
                }, 200);
            }
        });
        
        return {
            start: startTutorial,
            hide: hideTutorial,
            isActive: () => state.active
        };
    };
})();
