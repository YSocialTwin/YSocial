/**
 * Infinite Scroll Implementation for YSocial
 * 
 * This script implements infinite scrolling for pages that display posts.
 * It detects when the user scrolls near the bottom of the page and automatically
 * loads more content from the API.
 */

(function() {
    'use strict';

    // Configuration
    const config = {
        threshold: 0.9, // Load more when 90% of content is visible
        debounceDelay: 100, // Delay between scroll events in ms
        loaderHtml: `
            <div class="infinite-scroll-loader" style="text-align: center; padding: 2rem;">
                <div class="loader is-loading" style="margin: 0 auto;"></div>
                <p style="margin-top: 1rem; color: #7a7a7a;">Loading more posts...</p>
            </div>
        `
    };

    // State management
    let state = {
        isLoading: false,
        hasMore: true,
        currentPage: 1,
        apiEndpoint: null,
        postsContainer: null,
        sentinel: null
    };

    /**
     * Initialize infinite scrolling for a page
     * @param {Object} options - Configuration options
     * @param {string} options.apiEndpoint - The API endpoint to fetch posts from
     * @param {string} options.postsContainerId - The ID of the container that holds posts
     * @param {number} options.initialPage - The initial page number
     */
    function initInfiniteScroll(options) {
        if (!options || !options.apiEndpoint || !options.postsContainerId) {
            console.error('Invalid options provided to initInfiniteScroll');
            return;
        }

        state.apiEndpoint = options.apiEndpoint;
        state.currentPage = options.initialPage || 1;
        state.postsContainer = document.getElementById(options.postsContainerId);

        if (!state.postsContainer) {
            console.error('Posts container not found:', options.postsContainerId);
            return;
        }

        // Create and append sentinel element for intersection observer
        state.sentinel = document.createElement('div');
        state.sentinel.id = 'infinite-scroll-sentinel';
        state.sentinel.style.height = '1px';
        state.postsContainer.parentElement.appendChild(state.sentinel);

        // Set up Intersection Observer
        setupIntersectionObserver();

        // Remove old pagination buttons if they exist
        removeOldPagination();
    }

    /**
     * Set up Intersection Observer to detect when to load more content
     */
    function setupIntersectionObserver() {
        const options = {
            root: null,
            rootMargin: '200px',
            threshold: 0.1
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !state.isLoading && state.hasMore) {
                    loadMorePosts();
                }
            });
        }, options);

        observer.observe(state.sentinel);
    }

    /**
     * Remove old pagination buttons
     */
    function removeOldPagination() {
        const paginationWrap = document.querySelector('.load-more-wrap');
        if (paginationWrap) {
            paginationWrap.style.display = 'none';
        }
    }

    /**
     * Load more posts from the API
     */
    async function loadMorePosts() {
        if (state.isLoading || !state.hasMore) {
            return;
        }

        state.isLoading = true;
        showLoader();

        try {
            const nextPage = state.currentPage + 1;
            const response = await fetch(`${state.apiEndpoint}/${nextPage}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.html && data.html.trim().length > 0) {
                appendPostsHtml(data.html);
                state.currentPage = nextPage;
                state.hasMore = data.has_more;
            } else {
                state.hasMore = false;
                showEndMessage();
            }
        } catch (error) {
            console.error('Error loading more posts:', error);
            showErrorMessage();
        } finally {
            state.isLoading = false;
            hideLoader();
        }
    }

    /**
     * Append posts HTML to the container
     * @param {string} html - Rendered HTML string
     */
    function appendPostsHtml(html) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        
        // Append all child elements
        while (tempDiv.firstChild) {
            state.postsContainer.appendChild(tempDiv.firstChild);
        }

        // Initialize demo images for newly added posts
        initializeDemoImages();

        // Reinitialize dropdowns for newly added posts
        initializeDropdowns();
        
        // Initialize comment forms for newly added posts
        initializeCommentForms();
        
        // Initialize post comments toggle for newly added posts
        initializePostCommentsToggle();

        // Reinitialize any UI components that need it
        if (window.feather) {
            feather.replace();
        }
    }
    
    /**
     * Initialize post comments toggle for newly added content
     * This handles the comment section show/hide functionality
     */
    function initializePostCommentsToggle() {
        // Use jQuery if available to match global.js behavior
        if (typeof $ !== 'undefined') {
            // Find all comment fab buttons in the newly added posts
            $(state.postsContainer).find('.fab-wrapper.is-comment').each(function() {
                const $fab = $(this);
                
                // Remove any existing handlers to avoid duplicates
                $fab.off('click');
                
                // Add click handler (matches global.js initPostComments behavior)
                $fab.on('click', function(e) {
                    $(this)
                        .addClass('is-active')
                        .closest('.card')
                        .find('.content-wrap, .comments-wrap')
                        .toggleClass('is-hidden');
                    
                    var jump = $(this).closest('.is-post');
                    var new_position = $(jump).offset();
                    $('html, body')
                        .stop()
                        .animate({ scrollTop: new_position.top - 70 }, 500);
                    
                    e.preventDefault();
                    
                    setTimeout(function() {
                        $('.emojionearea-editor').val('');
                    }, 400);
                });
            });
            
            // Also handle close-comments buttons
            $(state.postsContainer).find('.close-comments').each(function() {
                const $closeBtn = $(this);
                $closeBtn.off('click');
                $closeBtn.on('click', function(e) {
                    $(this)
                        .closest('.card')
                        .find('.content-wrap, .comments-wrap')
                        .toggleClass('is-hidden');
                    
                    var jump = $(this).closest('.is-post');
                    var new_position = $(jump).offset();
                    $('html, body')
                        .stop()
                        .animate({ scrollTop: new_position.top - 70 }, 500);
                    
                    e.preventDefault();
                });
            });
        }
    }
    
    /**
     * Initialize comment forms for newly added content
     * Ensures comment forms are hidden and Reply links work correctly
     */
    function initializeCommentForms() {
        // Find all comment forms in the newly added posts and ensure they're hidden
        const commentForms = state.postsContainer.querySelectorAll('.comment_form');
        commentForms.forEach(function(form) {
            // Explicitly set display to none (CSS class should do this, but ensure it)
            if (!form.style.display || form.style.display === '') {
                form.style.display = 'none';
            }
        });
        
        // Ensure editLink function is available globally for inline onClick handlers
        // The function is defined in async_updates.js and should be accessible
        // This is just a check to ensure it's available
        if (typeof window.editLink === 'undefined' && typeof editLink !== 'undefined') {
            window.editLink = editLink;
        }
    }

    /**
     * Initialize dropdowns for newly added content
     * This replicates the dropdown initialization from global.js using jQuery
     */
    function initializeDropdowns() {
        // Use jQuery if available for consistency with global.js
        if (typeof $ !== 'undefined') {
            // Find all dropdown triggers in the posts container and reinitialize them
            $(state.postsContainer).find('.dropdown-trigger').each(function() {
                const $trigger = $(this);
                
                // Remove any existing handlers to avoid duplicates
                $trigger.off('click');
                
                // Add click handler (matches global.js behavior)
                $trigger.on('click', function(e) {
                    e.stopPropagation();
                    $('.dropdown-trigger').removeClass('is-active');
                    $(this).addClass('is-active');
                });
            });
        } else {
            // Fallback to vanilla JS if jQuery is not available
            const dropdownTriggers = state.postsContainer.querySelectorAll('.dropdown-trigger');
            
            dropdownTriggers.forEach(function(trigger) {
                // Remove any existing click handlers by cloning
                const newTrigger = trigger.cloneNode(true);
                trigger.parentNode.replaceChild(newTrigger, trigger);
                
                // Add click handler
                newTrigger.addEventListener('click', function(e) {
                    e.stopPropagation();
                    
                    // Remove active class from all other dropdowns
                    document.querySelectorAll('.dropdown-trigger').forEach(function(t) {
                        t.classList.remove('is-active');
                    });
                    
                    // Add active class to this dropdown
                    newTrigger.classList.add('is-active');
                });
            });
        }
    }

    /**
     * Initialize demo images by converting data-demo-src to src
     * This replicates the functionality from global.js for dynamically loaded content
     */
    function initializeDemoImages() {
        // Get all elements with data-demo-src within the posts container
        const demoImages = state.postsContainer.querySelectorAll('[data-demo-src]');
        demoImages.forEach(function(img) {
            const newSrc = img.getAttribute('data-demo-src');
            if (newSrc) {
                img.setAttribute('src', newSrc);
            }
        });

        // Also handle data-demo-background if present
        const demoBackgrounds = state.postsContainer.querySelectorAll('[data-demo-background]');
        demoBackgrounds.forEach(function(elem) {
            const newBg = elem.getAttribute('data-demo-background');
            if (newBg) {
                elem.style.backgroundImage = `url('${newBg}')`;
            }
        });
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} - Escaped text
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show loading indicator
     */
    function showLoader() {
        const loader = document.createElement('div');
        loader.id = 'infinite-scroll-loader';
        loader.innerHTML = config.loaderHtml;
        state.sentinel.parentElement.insertBefore(loader, state.sentinel);
    }

    /**
     * Hide loading indicator
     */
    function hideLoader() {
        const loader = document.getElementById('infinite-scroll-loader');
        if (loader) {
            loader.remove();
        }
    }

    /**
     * Show end of content message
     */
    function showEndMessage() {
        const message = document.createElement('div');
        message.className = 'infinite-scroll-end';
        message.style.cssText = 'text-align: center; padding: 2rem; color: #7a7a7a;';
        message.innerHTML = '<p>You\'ve reached the end of the feed</p>';
        state.sentinel.parentElement.insertBefore(message, state.sentinel);
    }

    /**
     * Show error message
     */
    function showErrorMessage() {
        const message = document.createElement('div');
        message.className = 'infinite-scroll-error';
        message.style.cssText = 'text-align: center; padding: 2rem; color: #f14668;';
        message.innerHTML = '<p>Error loading posts. Please try again later.</p>';
        state.sentinel.parentElement.insertBefore(message, state.sentinel);
        
        // Remove error message after 5 seconds
        setTimeout(() => {
            message.remove();
        }, 5000);
    }

    // Expose to global scope
    window.InfiniteScroll = {
        init: initInfiniteScroll
    };

})();
