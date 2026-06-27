(function() {
    'use strict';

    var AUTO_REFRESH_INTERVAL_MS = 30000;
    var TOP_REFRESH_SCROLL_THRESHOLD = 220;

    var state = {
        config: {},
        apiEndpoint: null,
        postsContainer: null,
        refreshNotice: null,
        refreshButton: null,
        autoRefreshTimer: null,
        isRefreshing: false,
        liveRefreshEnabled: false
    };

    function buildApiEndpoint(config) {
        return '/' + config.expId + '/api/photo/feed/' + config.userId + '/' + config.timeline + '/' + config.mode + '?tab=' + encodeURIComponent(config.tab || 'for_you');
    }

    function buildPageUrl(apiEndpoint, page) {
        var parts = String(apiEndpoint || '').split('?');
        var basePath = parts[0];
        var query = parts[1] ? '?' + parts[1] : '';
        return basePath + '/' + page + query;
    }

    function init() {
        var config = window.YS_DATA_PHOTO_FEED || {};
        if (config.page === undefined) {
            return;
        }

        stopAutoRefresh();

        state.config = config;
        state.apiEndpoint = buildApiEndpoint(config);
        state.postsContainer = document.getElementById('posts-container');
        state.liveRefreshEnabled = Number(config.page || 1) === 1;

        if (window.InfiniteScroll) {
            InfiniteScroll.init({
                apiEndpoint: state.apiEndpoint,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }

        if (!state.postsContainer) {
            return;
        }

        ensureRefreshNotice();
        hideRefreshNotice();

        if (state.liveRefreshEnabled) {
            startAutoRefresh();
        }
    }

    function ensureRefreshNotice() {
        if (state.refreshNotice && state.refreshButton) {
            return;
        }

        var existingNotice = document.getElementById('ys-feed-refresh-notice');
        if (!existingNotice) {
            existingNotice = document.createElement('div');
            existingNotice.id = 'ys-feed-refresh-notice';
            existingNotice.className = 'ys-feed-refresh-notice';
            existingNotice.hidden = true;
            existingNotice.innerHTML = [
                '<button type="button" class="ys-feed-refresh-notice__button">',
                '  <i data-feather="rotate-cw"></i>',
                '  <span>New posts available</span>',
                '</button>'
            ].join('');
            state.postsContainer.parentNode.insertBefore(existingNotice, state.postsContainer);
        }

        state.refreshNotice = existingNotice;
        state.refreshButton = existingNotice.querySelector('.ys-feed-refresh-notice__button');

        if (state.refreshButton && !state.refreshButton.dataset.bound) {
            state.refreshButton.addEventListener('click', function() {
                refreshFeed(true);
            });
            state.refreshButton.dataset.bound = '1';
        }
    }

    function initializeDynamicFeedContent(scope) {
        if (!scope) {
            return;
        }

        scope.querySelectorAll('[data-demo-src]').forEach(function(img) {
            var nextSrc = img.getAttribute('data-demo-src');
            if (nextSrc) {
                img.setAttribute('src', nextSrc);
            }
        });

        scope.querySelectorAll('[data-demo-background]').forEach(function(node) {
            var nextBackground = node.getAttribute('data-demo-background');
            if (nextBackground) {
                node.style.backgroundImage = "url('" + nextBackground + "')";
            }
        });

        if (window.feather) {
            window.feather.replace();
        }
    }

    function getTopRenderedPostId() {
        if (!state.postsContainer) {
            return null;
        }
        return extractTopPostId(state.postsContainer);
    }

    function extractTopPostId(root) {
        if (!root || !root.querySelector) {
            return null;
        }
        var firstPost = root.querySelector('[id^="feed-post-"]');
        if (!firstPost) {
            return null;
        }
        var postId = String(firstPost.id || '').replace('feed-post-', '');
        return postId || null;
    }

    function extractTopPostIdFromHtml(html) {
        if (!html || !html.trim()) {
            return null;
        }
        var temp = document.createElement('div');
        temp.innerHTML = html;
        return extractTopPostId(temp);
    }

    function shouldAutoRefreshFeed() {
        if (!state.liveRefreshEnabled) {
            return false;
        }
        if (document.hidden) {
            return false;
        }
        if (state.isRefreshing) {
            return false;
        }
        return window.scrollY < TOP_REFRESH_SCROLL_THRESHOLD;
    }

    function showRefreshNotice() {
        if (!state.refreshNotice) {
            return;
        }
        state.refreshNotice.hidden = false;
        state.refreshNotice.classList.add('is-visible');
    }

    function hideRefreshNotice() {
        if (!state.refreshNotice) {
            return;
        }
        state.refreshNotice.hidden = true;
        state.refreshNotice.classList.remove('is-visible');
    }

    function fetchFeedPage(page) {
        return fetch(buildPageUrl(state.apiEndpoint, page), {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        }).then(function(response) {
            if (!response.ok) {
                throw new Error('Unable to refresh feed.');
            }
            return response.json();
        });
    }

    function replaceFeedHtml(html) {
        if (!state.postsContainer) {
            return;
        }

        state.postsContainer.innerHTML = html;
        initializeDynamicFeedContent(state.postsContainer);
        hideRefreshNotice();

        if (window.InfiniteScroll) {
            InfiniteScroll.init({
                apiEndpoint: state.apiEndpoint,
                postsContainerId: 'posts-container',
                initialPage: 1
            });
        }
    }

    function refreshFeed(scrollToTop) {
        if (!state.liveRefreshEnabled || state.isRefreshing) {
            return Promise.resolve();
        }

        state.isRefreshing = true;
        return fetchFeedPage(1)
            .then(function(payload) {
                if (payload && payload.html) {
                    replaceFeedHtml(payload.html);
                    if (scrollToTop) {
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                    }
                }
            })
            .catch(function() {
                // Silent failure to preserve feed usability.
            })
            .finally(function() {
                state.isRefreshing = false;
            });
    }

    function probeForNewPosts() {
        if (!state.liveRefreshEnabled || state.isRefreshing) {
            return;
        }

        fetchFeedPage(1)
            .then(function(payload) {
                if (!payload || !payload.html) {
                    return;
                }
                var currentTop = getTopRenderedPostId();
                var nextTop = extractTopPostIdFromHtml(payload.html);
                if (!nextTop) {
                    return;
                }
                if (currentTop === null || nextTop !== currentTop) {
                    showRefreshNotice();
                }
            })
            .catch(function() {
                // Ignore silent probe failures.
            });
    }

    function startAutoRefresh() {
        if (!state.liveRefreshEnabled) {
            return;
        }
        stopAutoRefresh();
        state.autoRefreshTimer = window.setInterval(function() {
            if (!shouldAutoRefreshFeed()) {
                probeForNewPosts();
                return;
            }
            refreshFeed(false);
        }, AUTO_REFRESH_INTERVAL_MS);
    }

    function stopAutoRefresh() {
        if (state.autoRefreshTimer) {
            window.clearInterval(state.autoRefreshTimer);
            state.autoRefreshTimer = null;
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    window.PhotoFeed = {
        refreshFeed: refreshFeed,
        initializeDynamicFeedContent: initializeDynamicFeedContent
    };
    window.YSPhotoInitializeDynamicFeedContent = initializeDynamicFeedContent;
})();
