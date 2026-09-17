(function () {
    'use strict';

    var state = {
        config: null,
        form: null,
        input: null,
        tabs: [],
        grid: null,
        users: null,
        hashtags: null,
        summary: null,
        timer: null,
        currentKind: 'all'
    };

    function getConfig() {
        return window.YS_DATA_PHOTO_SEARCH || {};
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function buildQueryUrl(query, kind) {
        var config = state.config || {};
        var params = new URLSearchParams();
        if (query) {
            params.set('q', query);
        }
        if (kind && kind !== 'all') {
            params.set('kind', kind);
        }
        return (config.pageUrl || config.endpoint) + (params.toString() ? '?' + params.toString() : '');
    }

    function updateUrl(query, kind) {
        var url = buildQueryUrl(query, kind);
        window.history.replaceState({ query: query, kind: kind }, '', url);
    }

    function setActiveTab(kind) {
        state.currentKind = kind || 'all';
        state.tabs.forEach(function (tab) {
            tab.classList.toggle('is-active', tab.getAttribute('data-photo-search-kind') === state.currentKind);
        });
    }

    function renderPhotos(items) {
        if (!state.grid) {
            return;
        }
        if (!items || !items.length) {
            state.grid.innerHTML = '<div class="photo-search-page__empty">No photos matched your search yet.</div>';
            return;
        }

        state.grid.innerHTML = items.map(function (item) {
            var image = item.image || {};
            return [
                '<button type="button" class="photo-search-page__tile" data-photo-open-post="' + escapeHtml(item.post_id) + '">',
                '  <img src="' + escapeHtml(image.url || '') + '" data-demo-src="' + escapeHtml(image.url || '') + '" alt="' + escapeHtml(image.description || '') + '"/>',
                '  <div class="photo-search-page__tile-meta">',
                '    <strong>' + escapeHtml(item.author || '') + '</strong><br/>',
                '    <span>' + escapeHtml(item.display_time || '') + '</span>',
                '  </div>',
                '</button>'
            ].join('');
        }).join('');
    }

    function renderUsers(items) {
        if (!state.users) {
            return;
        }
        if (!items || !items.length) {
            state.users.innerHTML = '<div class="photo-overlay__empty">No people matched yet.</div>';
            return;
        }

        state.users.innerHTML = items.map(function (item) {
            return [
                '<div class="photo-search-page__user">',
                '  <a class="photo-search-page__user-main" href="/' + escapeHtml(state.config.expId) + '/photo/profile/' + escapeHtml(item.id) + '/recent/1">',
                '    <img src="' + escapeHtml(item.profile_pic || '') + '" data-demo-src="' + escapeHtml(item.profile_pic || '') + '" alt=""/>',
                '    <div class="photo-search-page__user-copy">',
                '      <strong>' + escapeHtml(item.username || '') + '</strong>',
                '      <small>' + escapeHtml(item.photo_count || 0) + ' photos</small>',
                '    </div>',
                '  </a>',
                '  <span class="photo-search-page__badge">' + escapeHtml(item.kind === 'page' ? 'Page' : 'User') + '</span>',
                '</div>'
            ].join('');
        }).join('');
    }

    function renderHashtags(items) {
        if (!state.hashtags) {
            return;
        }
        if (!items || !items.length) {
            state.hashtags.innerHTML = '<div class="photo-overlay__empty">No hashtags matched yet.</div>';
            return;
        }

        state.hashtags.innerHTML = items.map(function (item) {
            return [
                '<a class="photo-search-page__chip" href="/' + escapeHtml(state.config.expId) + '/photo/search?q=%23' + encodeURIComponent(item.hashtag || '') + '&kind=hashtags">',
                '  #' + escapeHtml(item.hashtag || ''),
                '  <span class="photo-search-page__badge">' + escapeHtml(item.photo_count || 0) + '</span>',
                '</a>'
            ].join('');
        }).join('');
    }

    function renderSummary(payload) {
        if (!state.summary || !payload) {
            return;
        }
        var query = payload.query || '';
        if (query) {
            state.summary.textContent = 'Showing ' + payload.counts.photos + ' photos, ' + payload.counts.users + ' people and ' + payload.counts.hashtags + ' hashtags for "' + query + '".';
        } else {
            state.summary.textContent = 'Browse recent photos, people and hashtags in this experiment.';
        }
    }

    function applyPayload(payload) {
        if (!payload || payload.ok === false) {
            return;
        }
        renderPhotos(payload.photos || []);
        renderUsers(payload.users || []);
        renderHashtags(payload.hashtags || []);
        renderSummary(payload);
        setActiveTab(payload.kind || 'all');
        updateUrl(payload.query || '', payload.kind || 'all');
        if (window.feather) {
            window.feather.replace();
        }
    }

    function fetchResults(query, kind) {
        var config = state.config || {};
        var params = new URLSearchParams();
        if (query) {
            params.set('q', query);
        }
        if (kind && kind !== 'all') {
            params.set('kind', kind);
        }

        return fetch(config.endpoint + (params.toString() ? '?' + params.toString() : ''), {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Search request failed');
            }
            return response.json();
        }).then(applyPayload).catch(function () {
            // Keep the previous results visible if the live query fails.
        });
    }

    function scheduleSearch() {
        if (state.timer) {
            window.clearTimeout(state.timer);
        }
        state.timer = window.setTimeout(function () {
            fetchResults(state.input ? state.input.value.trim() : '', state.currentKind);
        }, 220);
    }

    function bindEvents() {
        if (state.form) {
            state.form.addEventListener('submit', function (event) {
                event.preventDefault();
                fetchResults(state.input ? state.input.value.trim() : '', state.currentKind);
            });
        }

        if (state.grid) {
            state.grid.addEventListener('click', function (event) {
                var tile = event.target.closest('[data-photo-open-post]');
                if (!tile) {
                    return;
                }
                var opener = window.YSPhotoOpenPost;
                if (typeof opener === 'function') {
                    event.preventDefault();
                    event.stopPropagation();
                    opener(tile.getAttribute('data-photo-open-post'));
                }
            });
        }

        if (state.input) {
            state.input.addEventListener('input', scheduleSearch);
        }

        state.tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var nextKind = tab.getAttribute('data-photo-search-kind') || 'all';
                setActiveTab(nextKind);
                fetchResults(state.input ? state.input.value.trim() : '', nextKind);
            });
        });
    }

    function init() {
        state.config = getConfig();
        if (!state.config || !state.config.endpoint) {
            return;
        }

        state.form = document.querySelector('[data-photo-search-form]');
        state.input = document.querySelector('[data-photo-search-input]');
        state.tabs = Array.prototype.slice.call(document.querySelectorAll('[data-photo-search-kind]'));
        state.grid = document.querySelector('[data-photo-search-grid]');
        state.users = document.querySelector('[data-photo-search-users]');
        state.hashtags = document.querySelector('[data-photo-search-hashtags]');
        state.summary = document.querySelector('[data-photo-search-summary]');
        state.currentKind = String(state.config.kind || 'all').toLowerCase();

        bindEvents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
