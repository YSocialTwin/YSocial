(function () {
    'use strict';

    var state = {
        postOverlay: null,
        peopleOverlay: null,
        postDialog: null,
        peopleDialog: null,
        currentPeopleItems: [],
        currentPeopleKind: null,
        currentPeopleSearch: '',
        loggedId: '',
        expId: '',
    };

    function getContext() {
        return window.YS_DATA_PHOTO_FEED || window.YS_DATA_PHOTO_PROFILE || window.YS_DATA_PHOTO_CONTEXT || {};
    }

    function ensureOverlayElements() {
        if (!state.postOverlay) {
            state.postOverlay = document.querySelector('[data-photo-post-overlay]');
            state.peopleOverlay = document.querySelector('[data-photo-people-overlay]');
            if (state.postOverlay) {
                state.postDialog = state.postOverlay.querySelector('.photo-overlay__dialog');
            }
            if (state.peopleOverlay) {
                state.peopleDialog = state.peopleOverlay.querySelector('.photo-overlay__dialog');
            }
        }
        return Boolean(state.postOverlay && state.peopleOverlay);
    }

    function setBodyLocked(locked) {
        document.body.style.overflow = locked ? 'hidden' : '';
    }

    function closeAllOverlays() {
        if (state.postOverlay) {
            state.postOverlay.classList.remove('is-open');
            state.postOverlay.hidden = true;
        }
        if (state.peopleOverlay) {
            state.peopleOverlay.classList.remove('is-open');
            state.peopleOverlay.hidden = true;
        }
        setBodyLocked(false);
    }

    function openOverlay(overlay) {
        if (!overlay) {
            return;
        }
        overlay.hidden = false;
        overlay.classList.add('is-open');
        setBodyLocked(true);
        if (window.feather) {
            window.feather.replace();
        }
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderComment(comment) {
        return [
            '<div class="photo-overlay__comment">',
            '  <img src="' + escapeHtml(comment.profile_pic || '') + '" alt="">',
            '  <div class="photo-overlay__comment-copy">',
            '    <p><strong>' + escapeHtml(comment.username || '') + '</strong>' + escapeHtml(comment.body || '') + '</p>',
            '    <div class="photo-overlay__comment-meta">' + escapeHtml(comment.created_at || '') + ' · ' + escapeHtml(comment.likes || 0) + ' likes</div>',
            '  </div>',
            '</div>'
        ].join('');
    }

    function renderPeopleRow(item, kind) {
        var actionClass = item.action_label === 'Following' ? '' : ' is-primary';
        return [
            '<div class="photo-people-overlay__row">',
            '  <a class="photo-people-overlay__user" href="/' + escapeHtml(state.expId) + '/photo/profile/' + escapeHtml(item.id) + '/recent/1">',
            '    <img src="' + escapeHtml(item.profile_pic || '') + '" alt="">',
            '    <div class="photo-people-overlay__user-copy">',
            '      <strong>' + escapeHtml(item.username || '') + '</strong>',
            '      <span>' + escapeHtml(item.subtitle || '') + '</span>',
            '    </div>',
            '  </a>',
            '  <a class="photo-people-overlay__action' + actionClass + '" href="/' + escapeHtml(state.expId) + '/follow/' + escapeHtml(item.id) + '/' + escapeHtml(state.loggedId) + '">',
            '    ' + escapeHtml(item.action_label || 'Follow'),
            '  </a>',
            '</div>'
        ].join('');
    }

    function applyPeopleFilter() {
        if (!state.peopleOverlay) {
            return;
        }

        var list = state.peopleOverlay.querySelector('[data-photo-people-list]');
        var query = String(state.currentPeopleSearch || '').trim().toLowerCase();
        if (!list) {
            return;
        }

        var filtered = state.currentPeopleItems.filter(function (item) {
            if (!query) {
                return true;
            }
            return String(item.username || '').toLowerCase().indexOf(query) !== -1;
        });

        list.innerHTML = filtered.length
            ? filtered.map(function (item) { return renderPeopleRow(item, state.currentPeopleKind); }).join('')
            : '<div class="photo-overlay__empty">No matching accounts found.</div>';
    }

    function renderPeopleOverlay(payload, kind) {
        if (!state.peopleOverlay) {
            return;
        }
        state.currentPeopleItems = (payload && payload.items) ? payload.items : [];
        state.currentPeopleKind = kind;
        state.currentPeopleSearch = '';

        var title = state.peopleOverlay.querySelector('[data-photo-people-title]');
        var input = state.peopleOverlay.querySelector('[data-photo-people-search]');
        if (title) {
            title.textContent = kind === 'followers' ? 'Followers' : 'Following';
        }
        if (input) {
            input.value = '';
        }
        applyPeopleFilter();
        openOverlay(state.peopleOverlay);
    }

    function renderPostOverlay(payload) {
        if (!state.postOverlay || !payload || !payload.post) {
            return;
        }

        var post = payload.post;
        var image = state.postOverlay.querySelector('[data-photo-post-image]');
        var authorAvatar = state.postOverlay.querySelector('[data-photo-post-author-avatar]');
        var author = state.postOverlay.querySelector('[data-photo-post-author]');
        var time = state.postOverlay.querySelector('[data-photo-post-time]');
        var likes = state.postOverlay.querySelector('[data-photo-post-likes]');
        var comments = state.postOverlay.querySelector('[data-photo-post-comments]');
        var shares = state.postOverlay.querySelector('[data-photo-post-shares]');
        var likedBy = state.postOverlay.querySelector('[data-photo-post-liked-by]');
        var caption = state.postOverlay.querySelector('[data-photo-post-caption]');
        var commentsList = state.postOverlay.querySelector('[data-photo-post-comments-list]');

        if (image) {
            image.src = post.image && post.image.url ? post.image.url : '';
            image.alt = post.image && post.image.description ? post.image.description : '';
        }
        if (authorAvatar) {
            authorAvatar.src = post.profile_pic || '';
            authorAvatar.alt = post.author || '';
        }
        if (author) {
            author.textContent = post.author || '';
        }
        if (time) {
            time.textContent = post.display_time || '';
        }
        if (likes) {
            likes.innerHTML = '<i data-feather="heart"></i> ' + escapeHtml(post.likes_label || '0 likes');
        }
        if (comments) {
            comments.innerHTML = '<i data-feather="message-circle"></i> ' + escapeHtml((post.comments || 0) + ' comments');
        }
        if (shares) {
            shares.innerHTML = '<i data-feather="repeat"></i> ' + escapeHtml((post.shares || 0) + ' shares');
        }
        if (likedBy) {
            likedBy.textContent = post.liked_by_label || '';
            likedBy.style.display = post.liked_by_label ? 'block' : 'none';
        }
        if (caption) {
            caption.innerHTML = '<strong>' + escapeHtml(post.author || '') + '</strong> ' + escapeHtml(post.post || '');
        }
        if (commentsList) {
            var commentsHtml = (post.comments_list || []).map(renderComment).join('');
            commentsList.innerHTML = commentsHtml || '<div class="photo-overlay__empty">No comments yet.</div>';
        }

        if (window.feather) {
            window.feather.replace();
        }

        openOverlay(state.postOverlay);
    }

    function fetchJson(url) {
        return fetch(url, {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        });
    }

    function openPostOverlay(photoId) {
        var context = getContext();
        if (!context.expId || !photoId) {
            return;
        }
        fetchJson('/' + context.expId + '/api/photo/post/' + encodeURIComponent(photoId))
            .then(function (payload) {
                renderPostOverlay(payload);
            })
            .catch(function () {
                if (state.postOverlay) {
                    var commentsList = state.postOverlay.querySelector('[data-photo-post-comments-list]');
                    if (commentsList) {
                        commentsList.innerHTML = '<div class="photo-overlay__empty">Unable to load this photo.</div>';
                    }
                    openOverlay(state.postOverlay);
                }
            });
    }

    function openPeopleOverlay(kind) {
        var context = getContext();
        var endpointKey = kind === 'followers' ? 'followersEndpoint' : 'followingEndpoint';
        var endpoint = context[endpointKey];
        if (!context.expId || !endpoint) {
            return;
        }
        fetchJson(endpoint)
            .then(function (payload) {
                renderPeopleOverlay(payload, kind);
            })
            .catch(function () {
                if (state.peopleOverlay) {
                    var list = state.peopleOverlay.querySelector('[data-photo-people-list]');
                    if (list) {
                        list.innerHTML = '<div class="photo-overlay__empty">Unable to load this list.</div>';
                    }
                    openOverlay(state.peopleOverlay);
                }
            });
    }

    function bindEvents() {
        document.addEventListener('click', function (event) {
            var postTrigger = event.target.closest('[data-photo-open-post]');
            if (postTrigger) {
                event.preventDefault();
                openPostOverlay(postTrigger.getAttribute('data-photo-open-post'));
                return;
            }

            var peopleTrigger = event.target.closest('[data-photo-people-open]');
            if (peopleTrigger) {
                event.preventDefault();
                openPeopleOverlay(peopleTrigger.getAttribute('data-photo-people-open'));
                return;
            }

            var closeTrigger = event.target.closest('[data-photo-overlay-close]');
            if (closeTrigger) {
                event.preventDefault();
                closeAllOverlays();
                return;
            }

            if (event.target.matches('[data-photo-post-overlay]') || event.target.matches('[data-photo-people-overlay]')) {
                closeAllOverlays();
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeAllOverlays();
            }
        });

        if (state.peopleOverlay) {
            var search = state.peopleOverlay.querySelector('[data-photo-people-search]');
            if (search) {
                search.addEventListener('input', function () {
                    state.currentPeopleSearch = search.value || '';
                    applyPeopleFilter();
                });
            }
        }
    }

    function init() {
        var context = getContext();
        state.expId = String(context.expId || '');
        state.loggedId = String(context.loggedId || context.userId || '');
        if (!ensureOverlayElements()) {
            return;
        }
        bindEvents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
