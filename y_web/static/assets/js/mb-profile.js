var MB_PROFILE = (function() {
    function apiEndpointFor(config, mode) {
        return '/' + config.expId + '/api/profile/' + config.userId + '/' + mode;
    }

    function pageUrlFor(config, mode) {
        return '/' + config.expId + '/profile/' + config.userId + '/' + mode + '/1';
    }

    function setActiveMode(mode) {
        document.querySelectorAll('.ys-profile-activity-tab').forEach(function(button) {
            var isActive = button.getAttribute('data-profile-mode') === mode;
            button.classList.toggle('is-active', isActive);
            button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function initInfiniteScrollForMode(config, mode) {
        if (!window.InfiniteScroll) {
            return;
        }
        window.InfiniteScroll.init({
            apiEndpoint: apiEndpointFor(config, mode),
            postsContainerId: 'posts-container',
            initialPage: 1
        });
    }

    function refreshDynamicPostUi(container) {
        if (!container) {
            return;
        }

        container.querySelectorAll('[data-demo-src]').forEach(function(img) {
            var src = img.getAttribute('data-demo-src');
            if (src) {
                img.setAttribute('src', src);
            }
        });

        container.querySelectorAll('.like-count svg, .dislike-count svg, .share-count svg, .like-count svg *, .dislike-count svg *, .share-count svg *').forEach(function(icon) {
            icon.style.pointerEvents = 'none';
        });

        if (window.feather && typeof window.feather.replace === 'function') {
            window.feather.replace();
        }
    }

    function setLoadingState(activeButton, isLoading) {
        document.querySelectorAll('.ys-profile-activity-tab').forEach(function(button) {
            button.disabled = isLoading;
            button.classList.toggle('is-loading', isLoading && button === activeButton);
        });
    }

    function bindModeSwitching(config) {
        var postsContainer = document.getElementById('posts-container');
        if (!postsContainer) {
            return;
        }

        document.querySelectorAll('.ys-profile-activity-tab').forEach(function(button) {
            button.addEventListener('click', function() {
                var requestedMode = button.getAttribute('data-profile-mode');
                if (!requestedMode || requestedMode === config.mode) {
                    return;
                }

                setLoadingState(button, true);

                fetch(apiEndpointFor(config, requestedMode) + '/1', {
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                    .then(function(response) {
                        if (!response.ok) {
                            throw new Error('Unable to load profile activity.');
                        }
                        return response.json();
                    })
                    .then(function(payload) {
                        postsContainer.innerHTML = payload && payload.html ? payload.html : '';
                        refreshDynamicPostUi(postsContainer);
                        config.mode = requestedMode;
                        config.page = 1;
                        setActiveMode(requestedMode);
                        initInfiniteScrollForMode(config, requestedMode);

                        var nextUrl = button.getAttribute('data-profile-url') || pageUrlFor(config, requestedMode);
                        if (window.history && typeof window.history.pushState === 'function') {
                            window.history.pushState({ mode: requestedMode }, '', nextUrl);
                        }
                    })
                    .catch(function(error) {
                        console.error(error);
                        window.location.href = button.getAttribute('data-profile-url') || pageUrlFor(config, requestedMode);
                    })
                    .finally(function() {
                        setLoadingState(button, false);
                    });
            });
        });
    }

    function init() {
        var config = window.YS_DATA_MB_PROFILE || {};
        if (window.InfiniteScroll && config.page !== undefined) {
            window.InfiniteScroll.init({
                apiEndpoint: apiEndpointFor(config, config.mode),
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }
        bindModeSwitching(config);
    }

    document.addEventListener('DOMContentLoaded', init);

    return { init: init };
})();
