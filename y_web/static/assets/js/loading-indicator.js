/**
 * Loading Indicator Utility
 * 
 * Provides visual feedback for long-running operations through:
 * - Global overlay with spinner for blocking operations
 * - Status messages for user feedback
 * - Automatic dismissal on page reload
 */

(function() {
    'use strict';

    // Loading overlay state
    let loadingCount = 0;
    let loadingOverlay = null;
    let loadingMessage = null;

    /**
     * Initialize the loading overlay on DOM ready
     */
    function initLoadingOverlay() {
        if (loadingOverlay) return;

        // Create overlay element
        loadingOverlay = document.createElement('div');
        loadingOverlay.id = 'global-loading-overlay';
        loadingOverlay.className = 'global-loading-overlay';
        loadingOverlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 99999;
            backdrop-filter: blur(2px);
        `;

        // Create spinner container
        const spinnerContainer = document.createElement('div');
        spinnerContainer.style.cssText = `
            background: white;
            border-radius: 12px;
            padding: 40px 60px;
            text-align: center;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
            max-width: 400px;
        `;

        // Create spinner
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        spinner.style.cssText = `
            width: 50px;
            height: 50px;
            margin: 0 auto 20px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #5596e6;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        `;

        // Add keyframe animation via style tag if not already present
        if (!document.getElementById('loading-spinner-styles')) {
            const style = document.createElement('style');
            style.id = 'loading-spinner-styles';
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }

        // Create message element
        loadingMessage = document.createElement('div');
        loadingMessage.style.cssText = `
            font-size: 16px;
            color: #333;
            font-weight: 500;
            margin-top: 10px;
        `;
        loadingMessage.textContent = 'Loading...';

        spinnerContainer.appendChild(spinner);
        spinnerContainer.appendChild(loadingMessage);
        loadingOverlay.appendChild(spinnerContainer);
        document.body.appendChild(loadingOverlay);
    }

    /**
     * Show loading indicator with optional message
     * @param {string} message - Optional message to display
     */
    window.showLoading = function(message) {
        initLoadingOverlay();
        loadingCount++;
        
        if (message) {
            loadingMessage.textContent = message;
        } else {
            loadingMessage.textContent = 'Loading...';
        }
        
        loadingOverlay.style.display = 'flex';
    };

    /**
     * Hide loading indicator
     */
    window.hideLoading = function() {
        loadingCount = Math.max(0, loadingCount - 1);
        
        if (loadingCount === 0 && loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    };

    /**
     * Add loading indicator to a link or button
     * @param {HTMLElement} element - The element to add loading to
     * @param {string} message - Message to display while loading
     */
    window.addLoadingToElement = function(element, message) {
        if (!element) return;

        element.addEventListener('click', function(e) {
            // Don't show loading for javascript:void(0) links or if preventDefault was already called
            const href = element.getAttribute('href');
            if (href && href.includes('javascript:')) {
                return;
            }

            showLoading(message);
        });
    };

    /**
     * Add loading indicator to a form submission
     * @param {HTMLFormElement} form - The form element
     * @param {string} message - Message to display while loading
     */
    window.addLoadingToForm = function(form, message) {
        if (!form) return;

        form.addEventListener('submit', function(e) {
            showLoading(message);
        });
    };

    /**
     * Wrap an AJAX call with loading indicator
     * @param {string} message - Message to display while loading
     * @param {Function} ajaxFunction - Function that returns a Promise or has callbacks
     * @returns {Function} Wrapped function
     */
    window.withLoading = function(message, ajaxFunction) {
        return function(...args) {
            showLoading(message);
            
            const result = ajaxFunction.apply(this, args);
            
            // If it's a Promise
            if (result && typeof result.then === 'function') {
                result.finally(() => hideLoading());
            }
            // Otherwise, caller must call hideLoading() manually
            
            return result;
        };
    };

    /**
     * Show a toast notification
     * @param {string} message - Message to display
     * @param {string} type - Type of toast: 'success', 'error', 'warning', 'info'
     * @param {number} duration - Duration in milliseconds (default: 3000)
     */
    window.showToast = function(message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            min-width: 250px;
            max-width: 400px;
            padding: 16px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 100000;
            animation: slideIn 0.3s ease-out;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
        `;

        // Set colors based on type
        const colors = {
            success: { bg: '#d4edda', border: '#c3e6cb', text: '#155724' },
            error: { bg: '#f8d7da', border: '#f5c6cb', text: '#721c24' },
            warning: { bg: '#fff3cd', border: '#ffeeba', text: '#856404' },
            info: { bg: '#d1ecf1', border: '#bee5eb', text: '#0c5460' }
        };

        const color = colors[type] || colors.info;
        toast.style.background = color.bg;
        toast.style.border = `1px solid ${color.border}`;
        toast.style.color = color.text;

        // Add icon based on type
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };

        const icon = document.createElement('span');
        icon.textContent = icons[type] || icons.info;
        icon.style.cssText = `
            font-size: 18px;
            font-weight: bold;
        `;

        const messageSpan = document.createElement('span');
        messageSpan.textContent = message;
        messageSpan.style.flex = '1';

        toast.appendChild(icon);
        toast.appendChild(messageSpan);

        // Add animation style if not already present
        if (!document.getElementById('toast-styles')) {
            const style = document.createElement('style');
            style.id = 'toast-styles';
            style.textContent = `
                @keyframes slideIn {
                    from {
                        transform: translateX(400px);
                        opacity: 0;
                    }
                    to {
                        transform: translateX(0);
                        opacity: 1;
                    }
                }
                @keyframes slideOut {
                    from {
                        transform: translateX(0);
                        opacity: 1;
                    }
                    to {
                        transform: translateX(400px);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(toast);

        // Auto-dismiss
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    };

    // Auto-hide loading on page load/unload
    window.addEventListener('beforeunload', function() {
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    });

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLoadingOverlay);
    } else {
        initLoadingOverlay();
    }
})();
