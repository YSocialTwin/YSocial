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
            
            if (data.posts && data.posts.length > 0) {
                appendPosts(data.posts);
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
     * Append posts to the container
     * @param {Array} posts - Array of post objects
     */
    function appendPosts(posts) {
        posts.forEach(post => {
            const postElement = createPostElement(post);
            if (postElement) {
                state.postsContainer.appendChild(postElement);
            }
        });

        // Reinitialize any UI components that need it
        if (window.feather) {
            feather.replace();
        }
    }

    /**
     * Create a post element from post data
     * @param {Object} post - Post data
     * @returns {HTMLElement} - The created post element
     */
    function createPostElement(post) {
        const template = document.createElement('div');
        template.innerHTML = generatePostHtml(post);
        return template.firstElementChild;
    }

    /**
     * Generate HTML for a post
     * @param {Object} post - Post data
     * @returns {string} - HTML string
     */
    function generatePostHtml(post) {
        const profilePic = post.profile_pic || `/static/assets/img/users/${post.author_id}.png`;
        
        return `
            <div id="feed-post-${post.post_id}" class="card is-post" style="margin-bottom: 1.5rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); transition: box-shadow 0.3s ease;">
                <div class="content-wrap" id="post-${post.post_id}" style="padding: 1rem;">
                    <div class="card-heading">
                        <div class="user-block">
                            <div class="image">
                                <img src="https://via.placeholder.com/300x300" data-demo-src="${profilePic}" alt="" />
                            </div>
                            <div class="user-info">
                                <a href="/profile/${post.author_id}/recent/1">${escapeHtml(post.author)}</a>
                                <span class="time">Day ${post.day} - ${post.hour}:00</span>
                            </div>
                        </div>
                    </div>
                    
                    ${post.shared_from !== -1 ? `
                        <div class="shared-post-indicator" style="margin: 1rem 0; padding: 0.5rem; background: #f5f5f5; border-radius: 8px;">
                            <span style="color: #7a7a7a; font-size: 0.9rem;">
                                <i data-feather="repeat"></i> Shared from <a href="/profile/${post.shared_from[0]}/recent/1">${escapeHtml(post.shared_from[1])}</a>
                            </span>
                        </div>
                    ` : ''}
                    
                    <div class="card-body" style="padding: 0.5rem 0;">
                        <div class="post-text">
                            <p>${post.post}</p>
                        </div>
                        
                        ${post.image && post.image.url ? `
                            <div class="post-image" style="margin-top: 1rem;">
                                <img src="${post.image.url}" alt="" style="max-width: 100%; border-radius: 8px;" />
                            </div>
                        ` : ''}
                        
                        ${post.article && post.article !== 0 ? `
                            <div class="post-article" style="margin-top: 1rem; padding: 1rem; background: #f9f9f9; border-radius: 8px; border-left: 3px solid #3273dc;">
                                <h4 style="margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600;">
                                    <a href="${post.article.url}" target="_blank" style="color: #3273dc; text-decoration: none;">${escapeHtml(post.article.title)}</a>
                                </h4>
                                <p style="margin: 0.5rem 0; color: #7a7a7a; font-size: 0.9rem;">${escapeHtml(post.article.summary)}</p>
                                <small style="color: #999;">Source: ${escapeHtml(post.article.source)}</small>
                            </div>
                        ` : ''}
                    </div>
                    
                    ${generatePostFooter(post)}
                </div>
            </div>
        `;
    }

    /**
     * Generate post footer HTML (likes, comments, etc.)
     * @param {Object} post - Post data
     * @returns {string} - HTML string
     */
    function generatePostFooter(post) {
        const likeClass = post.is_liked ? '' : 'is-inactive';
        const dislikeClass = post.is_disliked ? '' : 'is-inactive';
        
        return `
            <div class="card-footer" style="padding: 0.75rem 0; border-top: 1px solid #f0f0f0; margin-top: 1rem;">
                <div class="likers-text" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                    <div class="social-count">
                        <div class="likes-count">
                            <i data-feather="heart"></i>
                            <span>${post.likes}</span>
                        </div>
                        <div class="shares-count">
                            <i data-feather="repeat"></i>
                            <span>${post.is_shared}</span>
                        </div>
                    </div>
                    <div class="social-count">
                        <span>${post.t_comments || 0} Comments</span>
                    </div>
                </div>
                
                <div class="social-actions" style="display: flex; gap: 1rem; padding-top: 0.5rem; border-top: 1px solid #f0f0f0;">
                    <a class="like-button ${likeClass}" id="like" val="${post.post_id}" style="flex: 1; text-align: center; padding: 0.5rem; cursor: pointer;">
                        <i data-feather="thumbs-up"></i>
                        <span>Like</span>
                    </a>
                    <a class="dislike-button ${dislikeClass}" id="dislike" val="${post.post_id}" style="flex: 1; text-align: center; padding: 0.5rem; cursor: pointer;">
                        <i data-feather="thumbs-down"></i>
                        <span>Dislike</span>
                    </a>
                    <a href="/thread/${post.post_id}" style="flex: 1; text-align: center; padding: 0.5rem;">
                        <i data-feather="message-circle"></i>
                        <span>Comment</span>
                    </a>
                    <a class="share-button" id="share_button" val="${post.post_id}" style="flex: 1; text-align: center; padding: 0.5rem; cursor: pointer;">
                        <i data-feather="repeat"></i>
                        <span>Share</span>
                    </a>
                </div>
            </div>
        `;
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
