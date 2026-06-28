(function () {
    'use strict';

    var state = {
        postOverlay: null,
        peopleOverlay: null,
        storyOverlay: null,
        storyCreateOverlay: null,
        shareOverlay: null,
        postDialog: null,
        peopleDialog: null,
        storyDialog: null,
        storyCreateDialog: null,
        shareDialog: null,
        profileEditOverlay: null,
        profileEditDialog: null,
        currentPeopleItems: [],
        currentPeopleKind: null,
        currentPeopleSearch: '',
        currentStory: null,
        currentStoryIndex: 0,
        currentStoryTrigger: null,
        currentPost: null,
        currentShareObjectUrl: '',
        currentShareFile: null,
        currentShareSubmitting: false,
        currentStoryCreateSelection: [],
        storyCreateSubmitting: false,
        storyGalleryItems: [],
        currentProfileEditSelection: {
            profilePic: '',
            profilePicData: ''
        },
        profileEditSubmitting: false,
        currentPhotoId: '',
        currentCommentTargetId: '',
        currentCommentTargetLabel: '',
        loggedId: '',
        expId: '',
    };

    function getContext() {
        return window.YS_DATA_PHOTO_FEED ||
            window.YS_DATA_PHOTO_PROFILE ||
            window.YS_DATA_PHOTO_SEARCH ||
            window.YS_DATA_PHOTO_STORIES ||
            window.YS_DATA_PHOTO_CONTEXT ||
            {};
    }

    function ensureOverlayElements() {
        if (!state.postOverlay || !state.peopleOverlay || !state.storyOverlay || !state.shareOverlay || !state.storyCreateOverlay || !state.profileEditOverlay) {
            state.postOverlay = document.querySelector('[data-photo-post-overlay]');
            state.peopleOverlay = document.querySelector('[data-photo-people-overlay]');
            state.storyOverlay = document.querySelector('[data-photo-story-overlay]');
            state.storyCreateOverlay = document.querySelector('[data-photo-story-create-overlay]');
            state.shareOverlay = document.querySelector('[data-photo-share-overlay]');
            state.profileEditOverlay = document.querySelector('[data-photo-profile-edit-overlay]');
            if (state.postOverlay) {
                state.postDialog = state.postOverlay.querySelector('.photo-overlay__dialog');
            }
            if (state.peopleOverlay) {
                state.peopleDialog = state.peopleOverlay.querySelector('.photo-overlay__dialog');
            }
            if (state.storyOverlay) {
                state.storyDialog = state.storyOverlay.querySelector('.photo-overlay__dialog');
            }
            if (state.storyCreateOverlay) {
                state.storyCreateDialog = state.storyCreateOverlay.querySelector('.photo-overlay__dialog');
            }
            if (state.shareOverlay) {
                state.shareDialog = state.shareOverlay.querySelector('.photo-overlay__dialog');
            }
            if (state.profileEditOverlay) {
                state.profileEditDialog = state.profileEditOverlay.querySelector('.photo-overlay__dialog');
            }
        }
        return Boolean(state.postOverlay && state.peopleOverlay && state.storyOverlay && state.shareOverlay && state.storyCreateOverlay && state.profileEditOverlay);
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
        if (state.storyOverlay) {
            state.storyOverlay.classList.remove('is-open');
            state.storyOverlay.hidden = true;
        }
        if (state.storyCreateOverlay) {
            state.storyCreateOverlay.classList.remove('is-open');
            state.storyCreateOverlay.hidden = true;
        }
        if (state.shareOverlay) {
            state.shareOverlay.classList.remove('is-open');
            state.shareOverlay.hidden = true;
        }
        if (state.profileEditOverlay) {
            state.profileEditOverlay.classList.remove('is-open');
            state.profileEditOverlay.hidden = true;
        }
        state.currentStory = null;
        state.currentStoryIndex = 0;
        state.currentStoryTrigger = null;
        state.currentPost = null;
        state.currentStoryCreateSelection = [];
        state.storyCreateSubmitting = false;
        state.profileEditSubmitting = false;
        state.currentProfileEditSelection = {
            profilePic: '',
            profilePicData: ''
        };
        clearSharePreview();
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

    function escapeCssSelector(value) {
        var text = String(value == null ? '' : value);
        if (window.CSS && typeof window.CSS.escape === 'function') {
            return window.CSS.escape(text);
        }
        return text.replace(/["\\]/g, '\\$&');
    }

    function normalizeComments(comments) {
        return Array.isArray(comments) ? comments : [];
    }

    function getCommentReplyCount(comment) {
        var replies = normalizeComments(comment && comment.replies);
        if (replies.length) {
            return replies.length;
        }
        var replyCount = parseInt(String(comment && comment.reply_count ? comment.reply_count : 0), 10);
        return Number.isNaN(replyCount) ? 0 : replyCount;
    }

    function renderCommentNode(comment, depth) {
        var authorHref = comment.user_href || '';
        var authorName = escapeHtml(comment.username || '');
        var bodyHtml = comment.body_html || escapeHtml(comment.body || '');
        var replies = normalizeComments(comment.replies);
        var replyCount = getCommentReplyCount(comment);
        var hasReplies = replyCount > 0;
        var classes = ['photo-overlay__comment'];
        if (hasReplies) {
            classes.push('is-collapsed');
        }
        if (depth > 0) {
            classes.push('photo-overlay__comment--reply');
        }

        return [
            '<article class="' + classes.join(' ') + '" data-comment-id="' + escapeHtml(comment.id || '') + '" data-parent-comment-id="' + escapeHtml(comment.parent_comment_id || '') + '">',
            '  <div class="photo-overlay__comment-main">',
            '    <img src="' + escapeHtml(comment.profile_pic || '') + '" alt="">',
            '    <div class="photo-overlay__comment-copy">',
            '      <p><strong>' + (authorHref ? '<a class="photo-inline-link" href="' + escapeHtml(authorHref) + '">' + authorName + '</a>' : authorName) + '</strong> ' + bodyHtml + '</p>',
            '      <div class="photo-overlay__comment-meta-row">',
            '        <span class="photo-overlay__comment-meta">' + escapeHtml(comment.created_at || '') + ' · ' + escapeHtml(comment.likes || 0) + ' likes</span>',
            '        <button type="button" class="photo-overlay__comment-toggle" data-photo-comment-reply data-comment-id="' + escapeHtml(comment.id || '') + '" data-comment-author="' + escapeHtml(comment.username || '') + '">Reply</button>',
            hasReplies ? '        <button type="button" class="photo-overlay__comment-toggle" data-photo-comment-toggle-replies data-photo-reply-count="' + escapeHtml(replyCount) + '">' + escapeHtml('View replies (' + replyCount + ')') + '</button>' : '',
            '      </div>',
            '    </div>',
            '  </div>',
            hasReplies ? '  <div class="photo-overlay__comment-thread">' + replies.map(function (reply) { return renderCommentNode(reply, depth + 1); }).join('') + '</div>' : '',
            '</article>'
        ].join('');
    }

    function renderCommentTree(comments) {
        var items = normalizeComments(comments);
        if (!items.length) {
            return '<div class="photo-overlay__empty">No comments yet.</div>';
        }
        return items.map(function (comment) {
            return renderCommentNode(comment, 0);
        }).join('');
    }

    function updateCommentsCount(delta, photoId) {
        var comments = state.postOverlay.querySelector('[data-photo-post-comments]');
        if (!comments) {
            return;
        }
        var current = parseInt(String(comments.textContent || '0').replace(/[^0-9]/g, ''), 10);
        if (Number.isNaN(current)) {
            current = 0;
        }
        comments.innerHTML = '<i data-feather="message-circle"></i> ' + escapeHtml((current + delta) + ' comments');
        if (photoId) {
            updatePostCardCounts(photoId, { comments: current + delta });
        }
        if (window.feather) {
            window.feather.replace();
        }
    }

    function findPostCard(photoId) {
        var postId = String(photoId || '').trim();
        if (!postId) {
            return null;
        }
        return document.getElementById('feed-post-' + postId) ||
            document.querySelector('[data-photo-post-card="' + escapeCssSelector(postId) + '"]');
    }

    function setNumericCounter(node, value) {
        if (!node) {
            return;
        }
        node.textContent = String(Number.isFinite(value) ? value : (parseInt(String(value || 0), 10) || 0));
    }

    function setPressedState(button, active) {
        if (!button) {
            return;
        }
        button.classList.toggle('photo-feed-card__action--active', !!active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
    }

    function updateOverlayCounter(selector, value, noun) {
        if (!state.postOverlay || !state.currentPhotoId) {
            return;
        }
        var node = state.postOverlay.querySelector(selector);
        if (!node) {
            return;
        }
        node.innerHTML = '<i data-feather="' + noun.icon + '"></i> ' + escapeHtml(value + ' ' + noun.label + (value === 1 ? '' : 's'));
    }

    function updatePostCardCounts(photoId, payload) {
        var card = findPostCard(photoId);
        if (!card) {
            if (state.postOverlay && String(state.currentPhotoId || '') === String(photoId || '')) {
                syncPostOverlayState(photoId, payload);
            }
            return;
        }

        if (typeof payload.likes === 'number') {
            setNumericCounter(card.querySelector('[data-photo-post-like-count]'), payload.likes);
        }
        if (typeof payload.comments === 'number') {
            setNumericCounter(card.querySelector('[data-photo-post-comment-count]'), payload.comments);
        }
        if (typeof payload.shares === 'number') {
            setNumericCounter(card.querySelector('[data-photo-post-share-count]'), payload.shares);
        }
        if (typeof payload.liked === 'boolean') {
            setPressedState(card.querySelector('[data-photo-post-like]'), payload.liked);
            card.classList.toggle('photo-feed-card__action--liked', payload.liked);
        }
        if (typeof payload.bookmarked === 'boolean') {
            setPressedState(card.querySelector('[data-photo-post-bookmark]'), payload.bookmarked);
            card.classList.toggle('photo-feed-card__action--saved', payload.bookmarked);
        }

        if (state.postOverlay && String(state.currentPhotoId || '') === String(photoId || '')) {
            syncPostOverlayState(photoId, payload);
        }
    }

    function syncPostOverlayState(photoId, payload) {
        if (!state.postOverlay || String(state.currentPhotoId || '') !== String(photoId || '')) {
            return;
        }

        if (typeof payload.likes === 'number') {
            updateOverlayCounter('[data-photo-post-likes]', payload.likes, { icon: 'heart', label: 'like' });
        }
        if (typeof payload.comments === 'number') {
            updateOverlayCounter('[data-photo-post-comments]', payload.comments, { icon: 'message-circle', label: 'comment' });
        }
        if (typeof payload.shares === 'number') {
            updateOverlayCounter('[data-photo-post-shares]', payload.shares, { icon: 'repeat', label: 'share' });
        }

        if (payload.liked_by_label !== undefined) {
            var likedBy = state.postOverlay.querySelector('[data-photo-post-liked-by]');
            if (likedBy) {
                likedBy.textContent = payload.liked_by_label || '';
                likedBy.style.display = payload.liked_by_label ? 'block' : 'none';
            }
        }
    }

    function clearCommentComposer() {
        var input = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-input]') : null;
        var target = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-target]') : null;
        var targetLabel = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-target-label]') : null;
        if (input) {
            input.value = '';
        }
        state.currentCommentTargetId = '';
        state.currentCommentTargetLabel = '';
        if (target) {
            target.classList.remove('is-visible');
        }
        if (targetLabel) {
            targetLabel.textContent = '';
        }
    }

    function setCommentReplyTarget(commentId, commentAuthor) {
        var target = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-target]') : null;
        var targetLabel = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-target-label]') : null;
        state.currentCommentTargetId = String(commentId || '').trim();
        state.currentCommentTargetLabel = String(commentAuthor || '').trim();
        if (target && targetLabel) {
            target.classList.add('is-visible');
            targetLabel.textContent = state.currentCommentTargetLabel
                ? 'Replying to @' + state.currentCommentTargetLabel
                : 'Replying';
        }
    }

    function bindComposerInteractions() {
        if (!state.postOverlay) {
            return;
        }

        var cancelButton = state.postOverlay.querySelector('[data-photo-comment-cancel]');
        var form = state.postOverlay.querySelector('[data-photo-comment-form]');
        if (cancelButton && cancelButton.getAttribute('data-photo-bound') !== 'true') {
            cancelButton.setAttribute('data-photo-bound', 'true');
            cancelButton.addEventListener('click', function (event) {
                event.preventDefault();
                clearCommentComposer();
                var input = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-input]') : null;
                if (input) {
                    input.focus();
                }
            });
        }

        if (form && form.getAttribute('data-photo-bound') !== 'true') {
            form.setAttribute('data-photo-bound', 'true');
            form.addEventListener('submit', function (event) {
                event.preventDefault();
                if (!state.expId || !state.currentPhotoId) {
                    return;
                }

                var input = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-input]') : null;
                var body = input ? String(input.value || '').trim() : '';
                if (!body) {
                    return;
                }

                var payload = {
                    body: body
                };
                if (state.currentCommentTargetId) {
                    payload.parent_comment_id = state.currentCommentTargetId;
                }

                var submitButton = form.querySelector('button[type="submit"]');
                if (submitButton) {
                    submitButton.disabled = true;
                }

                fetch('/' + state.expId + '/api/photo/post/' + encodeURIComponent(state.currentPhotoId) + '/comments', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(payload)
                }).then(function (response) {
                    if (!response.ok) {
                        throw new Error('Request failed');
                    }
                    return response.json();
                }).then(function (result) {
                    if (result && result.ok && result.comment) {
                        appendCommentNode(result.comment);
                        if (typeof result.comments === 'number') {
                            var card = findPostCard(state.currentPhotoId);
                            if (card) {
                                setNumericCounter(card.querySelector('[data-photo-post-comment-count]'), result.comments);
                            }
                        }
                        if (input) {
                            input.value = '';
                        }
                    }
                }).catch(function () {
                    if (state.postOverlay) {
                        var composerTarget = state.postOverlay.querySelector('[data-photo-comment-target-label]');
                        if (composerTarget) {
                            composerTarget.textContent = 'Unable to post comment. Please try again.';
                            var targetContainer = state.postOverlay.querySelector('[data-photo-comment-target]');
                            if (targetContainer) {
                                targetContainer.classList.add('is-visible');
                            }
                        }
                    }
                }).finally(function () {
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                });
            });
        }
    }

    function ensureCommentThreadContainer(commentNode) {
        return commentNode.querySelector(':scope > .photo-overlay__comment-thread');
    }

    function appendCommentNode(commentPayload) {
        if (!state.postOverlay || !commentPayload) {
            return;
        }
        var commentsList = state.postOverlay.querySelector('[data-photo-post-comments-list]');
        if (!commentsList) {
            return;
        }

        var commentHtml = renderCommentNode(commentPayload, commentPayload.parent_comment_id ? 1 : 0);
        var container = null;
        var parentId = String(commentPayload.parent_comment_id || '').trim();
        if (parentId) {
            var parentNode = commentsList.querySelector('[data-comment-id="' + escapeCssSelector(parentId) + '"]');
            if (parentNode) {
                container = ensureCommentThreadContainer(parentNode);
                if (!container) {
                    container = document.createElement('div');
                    container.className = 'photo-overlay__comment-thread';
                    parentNode.appendChild(container);
                }
                if (container) {
                    var toggle = parentNode.querySelector('[data-photo-comment-toggle-replies]');
                    if (!toggle) {
                        var metaRow = parentNode.querySelector('.photo-overlay__comment-meta-row');
                        if (metaRow) {
                            toggle = document.createElement('button');
                            toggle.type = 'button';
                            toggle.className = 'photo-overlay__comment-toggle';
                            toggle.setAttribute('data-photo-comment-toggle-replies', '');
                            toggle.setAttribute('data-photo-reply-count', '1');
                            toggle.textContent = 'View replies (1)';
                            metaRow.appendChild(toggle);
                        }
                    } else {
                        var replyCount = parseInt(String(toggle.getAttribute('data-photo-reply-count') || '0'), 10);
                        if (Number.isNaN(replyCount)) {
                            replyCount = 0;
                        }
                        replyCount += 1;
                        toggle.setAttribute('data-photo-reply-count', String(replyCount));
                        toggle.textContent = 'View replies (' + replyCount + ')';
                    }
                    parentNode.classList.remove('is-collapsed');
                    if (toggle) {
                        toggle.textContent = 'Hide replies';
                    }
                }
            }
        }

        if (!container) {
            var emptyState = commentsList.querySelector('.photo-overlay__empty');
            if (emptyState && commentsList.children.length === 1) {
                commentsList.innerHTML = commentHtml;
            } else {
                commentsList.insertAdjacentHTML('beforeend', commentHtml);
            }
        } else {
            container.insertAdjacentHTML('beforeend', commentHtml);
        }
        var insertedNode = null;
        if (container) {
            insertedNode = container.lastElementChild;
        } else {
            insertedNode = commentsList.lastElementChild;
        }
        if (insertedNode) {
            bindCommentInteractions(insertedNode);
        }
        if (window.feather) {
            window.feather.replace();
        }
        updateCommentsCount(1, state.currentPhotoId);
        clearCommentComposer();
    }

    function bindCommentInteractions(root) {
        var scope = root || document;
        scope.querySelectorAll('[data-photo-comment-toggle-replies]').forEach(function (button) {
            if (button.getAttribute('data-photo-bound') === 'true') {
                return;
            }
            button.setAttribute('data-photo-bound', 'true');
            button.addEventListener('click', function (event) {
                event.preventDefault();
                var comment = button.closest('[data-comment-id]');
                if (!comment) {
                    return;
                }
                var replyCount = button.getAttribute('data-photo-reply-count') || '';
                var isCollapsed = comment.classList.toggle('is-collapsed');
                button.textContent = isCollapsed ? ('View replies (' + replyCount + ')') : 'Hide replies';
                if (!isCollapsed) {
                    button.textContent = 'Hide replies';
                }
            });
        });

        scope.querySelectorAll('[data-photo-comment-reply]').forEach(function (button) {
            if (button.getAttribute('data-photo-bound') === 'true') {
                return;
            }
            button.setAttribute('data-photo-bound', 'true');
            button.addEventListener('click', function (event) {
                event.preventDefault();
                setCommentReplyTarget(button.getAttribute('data-comment-id'), button.getAttribute('data-comment-author'));
                var input = state.postOverlay ? state.postOverlay.querySelector('[data-photo-comment-input]') : null;
                if (input) {
                    input.focus();
                }
            });
        });
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

    function normalizeStoryImages(story) {
        var images = [];
        if (story && Array.isArray(story.image_urls)) {
            images = story.image_urls;
        } else if (story && typeof story.image_urls === 'string' && story.image_urls.trim()) {
            try {
                var parsed = JSON.parse(story.image_urls);
                if (Array.isArray(parsed)) {
                    images = parsed;
                }
            } catch (error) {
                images = [story.image_urls];
            }
        }

        images = images
            .map(function (item) { return String(item == null ? '' : item).trim(); })
            .filter(function (item) { return Boolean(item); });

        if (!images.length && story && story.image && story.image.url) {
            images = [String(story.image.url).trim()];
        }

        return images;
    }

    function getStoryItems() {
        var context = getContext();
        if (Array.isArray(context.stories)) {
            return context.stories;
        }
        if (Array.isArray(context.storyItems)) {
            return context.storyItems;
        }
        if (Array.isArray(context.profileStories)) {
            return context.profileStories;
        }
        return [];
    }

    function findStoryById(storyId) {
        var targetId = String(storyId || '').trim();
        if (!targetId) {
            return null;
        }
        var items = getStoryItems();
        for (var i = 0; i < items.length; i += 1) {
            var item = items[i] || {};
            var itemId = String(item.story_id || item.id || '').trim();
            if (itemId === targetId) {
                return item;
            }
        }
        return null;
    }

    function updateStoryCarousel() {
        if (!state.storyOverlay || !state.currentStory) {
            return;
        }

        var images = normalizeStoryImages(state.currentStory);
        if (!images.length) {
            images = [''];
        }
        if (state.currentStoryIndex >= images.length) {
            state.currentStoryIndex = 0;
        }
        if (state.currentStoryIndex < 0) {
            state.currentStoryIndex = images.length - 1;
        }

        var image = state.storyOverlay.querySelector('[data-photo-story-image]');
        var prev = state.storyOverlay.querySelector('[data-photo-story-prev]');
        var next = state.storyOverlay.querySelector('[data-photo-story-next]');
        var counter = state.storyOverlay.querySelector('[data-photo-story-counter]');
        if (image) {
            image.src = images[state.currentStoryIndex] || '';
            image.alt = state.currentStory.description || state.currentStory.title || '';
        }
        if (prev) {
            prev.disabled = images.length <= 1;
        }
        if (next) {
            next.disabled = images.length <= 1;
        }
        if (counter) {
            counter.textContent = (state.currentStoryIndex + 1) + ' / ' + images.length;
        }
    }

    function renderStoryOverlay(story) {
        if (!state.storyOverlay || !story) {
            return;
        }

        state.currentStory = story;
        state.currentStoryIndex = 0;

        var authorAvatar = state.storyOverlay.querySelector('[data-photo-story-author-avatar]');
        var author = state.storyOverlay.querySelector('[data-photo-story-author]');
        var time = state.storyOverlay.querySelector('[data-photo-story-time]');
        var title = state.storyOverlay.querySelector('[data-photo-story-title]');
        var description = state.storyOverlay.querySelector('[data-photo-story-description]');
        var images = state.storyOverlay.querySelector('[data-photo-story-images]');
        var views = state.storyOverlay.querySelector('[data-photo-story-views]');
        var caption = state.storyOverlay.querySelector('[data-photo-story-caption]');

        if (authorAvatar) {
            authorAvatar.src = story.profile_pic || '';
            authorAvatar.alt = story.username || '';
        }
        if (author) {
            author.textContent = story.username || '';
        }
        if (time) {
            time.textContent = story.display_time || '';
        }
        if (title) {
            title.textContent = story.title || 'Story';
        }
        if (description) {
            description.textContent = story.description || '';
        }
        if (images) {
            var imageCount = normalizeStoryImages(story).length;
            images.innerHTML = '<i data-feather="image"></i> ' + escapeHtml(imageCount + ' images');
        }
        if (views) {
            views.innerHTML = '<i data-feather="eye"></i> ' + escapeHtml((story.view_count || 0) + ' views');
        }
        if (caption) {
            caption.innerHTML = story.caption ? story.caption : '';
            caption.style.display = story.caption ? 'block' : 'none';
        }

        updateStoryCarousel();

        if (window.feather) {
            window.feather.replace();
        }

        openOverlay(state.storyOverlay);
    }

    function getStoryCreateElements() {
        if (!state.storyCreateOverlay) {
            return {};
        }
        return {
            author: state.storyCreateOverlay.querySelector('[data-photo-story-create-author]'),
            authorAvatar: state.storyCreateOverlay.querySelector('[data-photo-story-create-author-avatar]'),
            title: state.storyCreateOverlay.querySelector('[data-photo-story-create-title]'),
            submit: state.storyCreateOverlay.querySelector('[data-photo-story-create-submit]'),
            gallery: state.storyCreateOverlay.querySelector('[data-photo-story-create-gallery]'),
            selected: state.storyCreateOverlay.querySelector('[data-photo-story-create-selected]'),
            preview: state.storyCreateOverlay.querySelector('[data-photo-story-create-preview]'),
            previewMeta: state.storyCreateOverlay.querySelector('[data-photo-story-create-preview-meta]'),
            titleInput: state.storyCreateOverlay.querySelector('[data-photo-story-create-input-title]'),
            descriptionInput: state.storyCreateOverlay.querySelector('[data-photo-story-create-input-description]'),
            counter: state.storyCreateOverlay.querySelector('[data-photo-story-create-counter]'),
            helper: state.storyCreateOverlay.querySelector('[data-photo-story-create-helper]'),
            form: state.storyCreateOverlay.querySelector('[data-photo-story-create-form]')
        };
    }

    function syncStoryCreateAuthor() {
        var elements = getStoryCreateElements();
        var sidebar = document.querySelector('.photo-sidebar__profile');
        var avatar = sidebar ? sidebar.querySelector('img') : null;
        var name = sidebar ? sidebar.querySelector('strong') : null;
        if (elements.authorAvatar && avatar) {
            elements.authorAvatar.src = avatar.getAttribute('src') || '';
            elements.authorAvatar.alt = avatar.getAttribute('alt') || '';
        }
        if (elements.author && name) {
            elements.author.textContent = name.textContent || '';
        }
    }

    function findStoryCreateGalleryItem(photoId) {
        var targetId = String(photoId || '').trim();
        if (!targetId) {
            return null;
        }
        for (var i = 0; i < state.storyGalleryItems.length; i += 1) {
            var item = state.storyGalleryItems[i] || {};
            var itemId = String(item.post_id || item.photo_id || item.id || '').trim();
            if (itemId === targetId) {
                return item;
            }
        }
        return null;
    }

    function getStoryCreateSelectedItems() {
        var items = [];
        for (var i = 0; i < state.currentStoryCreateSelection.length; i += 1) {
            var item = findStoryCreateGalleryItem(state.currentStoryCreateSelection[i]);
            if (item) {
                items.push(item);
            }
        }
        return items;
    }

    function updateStoryCreateSubmitState() {
        var elements = getStoryCreateElements();
        if (!elements.submit) {
            return;
        }
        elements.submit.textContent = 'Share';
        var title = elements.titleInput ? String(elements.titleInput.value || '').trim() : '';
        var description = elements.descriptionInput ? String(elements.descriptionInput.value || '').trim() : '';
        var canSubmit = !state.storyCreateSubmitting && state.currentStoryCreateSelection.length > 0 && Boolean(title) && Boolean(description);
        elements.submit.disabled = !canSubmit;
        if (elements.counter) {
            elements.counter.textContent = state.currentStoryCreateSelection.length + ' / 5 photos selected';
        }
    }

    function renderStoryCreateSelection() {
        var elements = getStoryCreateElements();
        if (!elements.selected || !elements.preview) {
            return;
        }

        var selectedItems = getStoryCreateSelectedItems();
        if (!selectedItems.length) {
            elements.selected.innerHTML = '<div class="photo-story-create-overlay__selected-empty">Select up to 5 photos from your gallery.</div>';
            elements.preview.removeAttribute('src');
            elements.preview.alt = 'No photo selected';
            if (elements.previewMeta) {
                elements.previewMeta.textContent = 'No photo selected yet';
            }
            updateStoryCreateSubmitState();
            if (window.feather) {
                window.feather.replace();
            }
            return;
        }

        elements.selected.innerHTML = selectedItems.map(function (item, index) {
            var image = item.image || {};
            return [
                '<button type="button" class="photo-story-create-overlay__selected-item" data-photo-story-create-photo="' + escapeHtml(item.post_id || item.photo_id || item.id || '') + '">',
                '  <img src="' + escapeHtml(image.url || '') + '" alt="' + escapeHtml(image.description || '') + '"/>',
                '  <span>' + escapeHtml(index + 1) + '</span>',
                '</button>'
            ].join('');
        }).join('');

        var first = selectedItems[0] || {};
        var firstImage = first.image || {};
        elements.preview.src = firstImage.url || '';
        elements.preview.alt = firstImage.description || first.post || first.title || 'Selected photo';
        if (elements.previewMeta) {
            elements.previewMeta.textContent = selectedItems.length + ' selected';
        }
        updateStoryCreateSubmitState();
        if (window.feather) {
            window.feather.replace();
        }
    }

    function renderStoryCreateGallery() {
        var elements = getStoryCreateElements();
        if (!elements.gallery) {
            return;
        }

        var items = Array.isArray(state.storyGalleryItems) ? state.storyGalleryItems : [];
        if (!items.length) {
            elements.gallery.innerHTML = '<div class="photo-overlay__empty">No photos are available in your gallery yet.</div>';
            renderStoryCreateSelection();
            return;
        }

        elements.gallery.innerHTML = items.map(function (item) {
            var image = item.image || {};
            var photoId = String(item.post_id || item.photo_id || item.id || '').trim();
            var selected = state.currentStoryCreateSelection.indexOf(photoId) !== -1;
            return [
                '<button type="button" class="photo-story-create-overlay__tile' + (selected ? ' is-selected' : '') + '" data-photo-story-create-photo="' + escapeHtml(photoId) + '">',
                '  <img src="' + escapeHtml(image.url || '') + '" alt="' + escapeHtml(image.description || item.post || '') + '"/>',
                '  <span class="photo-story-create-overlay__tile-check"><i data-feather="check"></i></span>',
                '</button>'
            ].join('');
        }).join('');

        renderStoryCreateSelection();
    }

    function toggleStoryCreatePhoto(photoId) {
        var photoKey = String(photoId || '').trim();
        if (!photoKey) {
            return;
        }
        var index = state.currentStoryCreateSelection.indexOf(photoKey);
        if (index !== -1) {
            state.currentStoryCreateSelection.splice(index, 1);
        } else if (state.currentStoryCreateSelection.length < 5) {
            state.currentStoryCreateSelection.push(photoKey);
        }
        renderStoryCreateGallery();
    }

    function clearStoryCreateState() {
        state.currentStoryCreateSelection = [];
        state.storyCreateSubmitting = false;
        var elements = getStoryCreateElements();
        if (elements.titleInput) {
            elements.titleInput.value = '';
        }
        if (elements.descriptionInput) {
            elements.descriptionInput.value = '';
        }
        renderStoryCreateGallery();
        updateStoryCreateSubmitState();
    }

    function openStoryCreateOverlay() {
        if (!state.storyCreateOverlay) {
            return;
        }
        syncStoryCreateAuthor();
        clearStoryCreateState();
        openOverlay(state.storyCreateOverlay);
        renderStoryCreateGallery();
    }

    function getProfileEditContext() {
        var context = getContext();
        return {
            data: context.profileEditData || {},
            profilePics: Array.isArray(context.availableProfilePics) ? context.availableProfilePics.slice() : []
        };
    }

    function getProfileEditElements() {
        if (!state.profileEditOverlay) {
            return {};
        }
        return {
            avatar: state.profileEditOverlay.querySelector('[data-photo-profile-edit-avatar]'),
            username: state.profileEditOverlay.querySelector('[data-photo-profile-edit-username]'),
            avatarPreview: state.profileEditOverlay.querySelector('[data-photo-profile-edit-avatar-preview]'),
            avatarGallery: state.profileEditOverlay.querySelector('[data-photo-profile-edit-avatar-gallery]'),
            avatarInput: state.profileEditOverlay.querySelector('[data-photo-profile-edit-avatar-input]'),
            uploadInput: state.profileEditOverlay.querySelector('[data-photo-profile-edit-upload]'),
            uploadTrigger: state.profileEditOverlay.querySelector('[data-photo-profile-edit-upload-trigger]'),
            avatarCount: state.profileEditOverlay.querySelector('[data-photo-profile-edit-avatar-count]'),
            form: state.profileEditOverlay.querySelector('[data-photo-profile-edit-form]'),
            submit: state.profileEditOverlay.querySelector('[data-photo-profile-edit-submit]'),
            email: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-email]'),
            age: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-age]'),
            gender: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-gender]'),
            nationality: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-nationality]'),
            language: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-language]'),
            leaning: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-leaning]'),
            education: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-education]'),
            bio: state.profileEditOverlay.querySelector('[data-photo-profile-edit-input-bio]')
        };
    }

    function syncProfileEditHeader() {
        var elements = getProfileEditElements();
        var context = getProfileEditContext();
        var data = context.data || {};
        var avatarValue = state.currentProfileEditSelection.profilePicData || state.currentProfileEditSelection.profilePic || data.profile_pic || '';
        if (elements.avatar) {
            elements.avatar.src = avatarValue || '';
            elements.avatar.alt = data.username || '';
        }
        if (elements.username) {
            elements.username.textContent = data.username || '';
        }
        if (elements.avatarInput) {
            elements.avatarInput.value = avatarValue || '';
        }
    }

    function setProfileEditFieldValues() {
        var elements = getProfileEditElements();
        var context = getProfileEditContext();
        var data = context.data || {};
        if (elements.email) {
            elements.email.value = data.email || '';
        }
        if (elements.age) {
            elements.age.value = data.age || 0;
        }
        if (elements.gender) {
            elements.gender.value = data.gender || '';
        }
        if (elements.nationality) {
            elements.nationality.value = data.nationality || '';
        }
        if (elements.language) {
            elements.language.value = data.language || '';
        }
        if (elements.leaning) {
            elements.leaning.value = data.leaning || '';
        }
        if (elements.education) {
            elements.education.value = data.education_level || '';
        }
        if (elements.bio) {
            elements.bio.value = data.bio || '';
        }
    }

    function updateProfileEditSubmitState() {
        var elements = getProfileEditElements();
        if (!elements.submit) {
            return;
        }
        var canSubmit = !state.profileEditSubmitting;
        if (elements.submit) {
            elements.submit.disabled = !canSubmit;
            elements.submit.textContent = state.profileEditSubmitting ? 'Saving...' : 'Save';
        }
    }

    function renderProfileEditGallery(kind) {
        var elements = getProfileEditElements();
        var context = getProfileEditContext();
        var data = context.data || {};
        var items = context.profilePics;
        var selectedValue = state.currentProfileEditSelection.profilePicData || state.currentProfileEditSelection.profilePic || data.profile_pic || '';
        var gallery = elements.avatarGallery;
        var preview = elements.avatarPreview;
        var count = elements.avatarCount;
        var optionAttribute = 'data-photo-profile-edit-avatar-option';
        var optionClass = 'photo-profile-edit-overlay__option';

        if (!gallery) {
            return;
        }

        if (count) {
            count.textContent = items.length ? (items.length + ' available') : 'No options';
        }

        if (!items.length) {
            gallery.innerHTML = '<div class="photo-overlay__empty">No profile pictures are available yet.</div>';
        } else {
            gallery.innerHTML = items.map(function (item) {
                var isSelected = String(item || '') === String(selectedValue || '');
                return [
                    '<button type="button" class="' + optionClass + (isSelected ? ' is-selected' : '') + '" ' + optionAttribute + '="' + escapeHtml(item) + '">',
                    '  <img src="' + escapeHtml(item) + '" alt="">',
                    '</button>'
                ].join('');
            }).join('');
        }

        if (preview) {
            if (selectedValue || items.length) {
                preview.src = selectedValue || items[0];
            } else {
                preview.removeAttribute('src');
            }
            preview.alt = 'Selected profile picture';
        }
    }

    function renderProfileEditOverlay() {
        if (!state.profileEditOverlay) {
            return;
        }
        syncProfileEditHeader();
        setProfileEditFieldValues();
        renderProfileEditGallery('avatar');
        updateProfileEditSubmitState();
        if (window.feather) {
            window.feather.replace();
        }
    }

    function setProfileEditSelection(value) {
        state.currentProfileEditSelection.profilePic = String(value || '').trim();
        state.currentProfileEditSelection.profilePicData = '';
        syncProfileEditHeader();
        renderProfileEditGallery('avatar');
        updateProfileEditSubmitState();
        if (window.feather) {
            window.feather.replace();
        }
    }

    function readFileAsDataUrl(file) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function (event) {
                resolve(event && event.target ? event.target.result : '');
            };
            reader.onerror = function () {
                reject(new Error('Unable to read file'));
            };
            reader.readAsDataURL(file);
        });
    }

    function cropDataUrlToSquare(dataUrl) {
        return new Promise(function (resolve) {
            var image = new Image();
            image.onload = function () {
                try {
                    var size = Math.min(image.width || 0, image.height || 0);
                    if (!size) {
                        resolve(dataUrl);
                        return;
                    }
                    var canvas = document.createElement('canvas');
                    canvas.width = size;
                    canvas.height = size;
                    var context2d = canvas.getContext('2d');
                    if (!context2d) {
                        resolve(dataUrl);
                        return;
                    }
                    var offsetX = Math.max(0, Math.floor((image.width - size) / 2));
                    var offsetY = Math.max(0, Math.floor((image.height - size) / 2));
                    context2d.drawImage(image, offsetX, offsetY, size, size, 0, 0, size, size);
                    resolve(canvas.toDataURL('image/png'));
                } catch (error) {
                    resolve(dataUrl);
                }
            };
            image.onerror = function () {
                resolve(dataUrl);
            };
            image.src = dataUrl;
        });
    }

    function setProfileEditUploadedImage(dataUrl) {
        state.currentProfileEditSelection.profilePic = '';
        state.currentProfileEditSelection.profilePicData = String(dataUrl || '').trim();
        syncProfileEditHeader();
        renderProfileEditGallery('avatar');
        updateProfileEditSubmitState();
        if (window.feather) {
            window.feather.replace();
        }
    }

    function handleProfileEditUpload(file) {
        if (!file) {
            return;
        }
        readFileAsDataUrl(file).then(function (dataUrl) {
            if (!dataUrl) {
                return dataUrl;
            }
            return cropDataUrlToSquare(dataUrl);
        }).then(function (croppedDataUrl) {
            if (croppedDataUrl) {
                setProfileEditUploadedImage(croppedDataUrl);
            }
        }).catch(function () {
            // Keep the previous selection if the image cannot be processed.
        });
    }

    function openProfileEditOverlay() {
        if (!state.profileEditOverlay) {
            return;
        }
        state.profileEditSubmitting = false;
        var context = getProfileEditContext();
        state.currentProfileEditSelection = {
            profilePic: context.data.profile_pic || (context.profilePics.length ? context.profilePics[0] : ''),
            profilePicData: ''
        };
        openOverlay(state.profileEditOverlay);
        renderProfileEditOverlay();
    }

    function applyProfileEditResult(result) {
        if (!result || !result.ok) {
            return;
        }

        var context = getContext();
        if (context.profileEditData) {
            context.profileEditData.profile_pic = typeof result.profile_pic !== 'undefined' ? result.profile_pic : (context.profileEditData.profile_pic || '');
            context.profileEditData.email = typeof result.email !== 'undefined' ? result.email : (context.profileEditData.email || '');
            context.profileEditData.age = typeof result.age !== 'undefined' ? result.age : context.profileEditData.age;
            context.profileEditData.gender = typeof result.gender !== 'undefined' ? result.gender : (context.profileEditData.gender || '');
            context.profileEditData.nationality = typeof result.nationality !== 'undefined' ? result.nationality : (context.profileEditData.nationality || '');
            context.profileEditData.language = typeof result.language !== 'undefined' ? result.language : (context.profileEditData.language || '');
            context.profileEditData.leaning = typeof result.leaning !== 'undefined' ? result.leaning : (context.profileEditData.leaning || '');
            context.profileEditData.education_level = typeof result.education_level !== 'undefined' ? result.education_level : (context.profileEditData.education_level || '');
            context.profileEditData.bio = typeof result.bio !== 'undefined' ? result.bio : (context.profileEditData.bio || '');
        }

        state.currentProfileEditSelection.profilePic = result.profile_pic || state.currentProfileEditSelection.profilePic || '';
        state.currentProfileEditSelection.profilePicData = '';

        var avatar = document.querySelector('.photo-profile-avatar img');
        if (avatar && result.profile_pic) {
            avatar.src = result.profile_pic;
        }
        var sidebarAvatar = document.querySelector('.photo-sidebar__profile img');
        if (sidebarAvatar && result.profile_pic) {
            sidebarAvatar.src = result.profile_pic;
        }
        var overlayAvatar = state.profileEditOverlay ? state.profileEditOverlay.querySelector('[data-photo-profile-edit-avatar]') : null;
        if (overlayAvatar && result.profile_pic) {
            overlayAvatar.src = result.profile_pic;
        }
        var noteBubble = document.querySelector('.photo-profile-note');
        if (noteBubble) {
            if (result.bio) {
                noteBubble.textContent = result.bio;
                noteBubble.style.display = 'block';
            } else if (context.profileEditData && context.profileEditData.bio) {
                noteBubble.textContent = context.profileEditData.bio;
                noteBubble.style.display = 'block';
            } else {
                noteBubble.style.display = 'none';
            }
        }
    }

    function submitProfileEditOverlay() {
        var elements = getProfileEditElements();
        if (!elements.form || state.profileEditSubmitting) {
            return;
        }
        var context = getProfileEditContext();
        var data = context.data || {};
        var formData = new FormData();
        formData.append('email', elements.email ? String(elements.email.value || '').trim() : (data.email || ''));
        formData.append('age', elements.age ? String(elements.age.value || data.age || 0).trim() : String(data.age || 0));
        formData.append('gender', elements.gender ? String(elements.gender.value || '').trim() : (data.gender || ''));
        formData.append('nationality', elements.nationality ? String(elements.nationality.value || '').trim() : (data.nationality || ''));
        formData.append('language', elements.language ? String(elements.language.value || '').trim() : (data.language || ''));
        formData.append('leaning', elements.leaning ? String(elements.leaning.value || '').trim() : (data.leaning || ''));
        formData.append('education_level', elements.education ? String(elements.education.value || '').trim() : (data.education_level || ''));
        formData.append('bio', elements.bio ? String(elements.bio.value || '').trim() : (data.bio || ''));
        if (state.currentProfileEditSelection.profilePicData) {
            formData.append('profile_pic_data', state.currentProfileEditSelection.profilePicData);
        } else {
            formData.append('profile_pic', state.currentProfileEditSelection.profilePic || data.profile_pic || '');
        }

        var endpoint = '/' + state.expId + '/api/photo/profile/update';
        state.profileEditSubmitting = true;
        updateProfileEditSubmitState();

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (result) {
            if (result && result.ok) {
                applyProfileEditResult(result);
                closeAllOverlays();
            }
        }).catch(function () {
            if (elements.submit) {
                elements.submit.textContent = 'Unable to save';
            }
        }).finally(function () {
            state.profileEditSubmitting = false;
            updateProfileEditSubmitState();
        });
    }

    function insertProfileStory(story) {
        if (!story) {
            return;
        }
        var context = getContext();
        if (Array.isArray(context.stories)) {
            context.stories.unshift(story);
        }

        var list = document.querySelector('[data-photo-profile-stories-list]');
        if (!list) {
            return;
        }
        var imageUrl = (story.image && story.image.url) || (Array.isArray(story.image_urls) && story.image_urls[0]) || '';
        var storyId = String(story.story_id || story.id || '').trim();
        if (!storyId || !imageUrl) {
            return;
        }
        var node = document.createElement('a');
        node.className = 'photo-profile-story';
        node.href = '#';
        node.setAttribute('data-photo-open-story', storyId);
        node.setAttribute('data-photo-story-index', '0');
        node.innerHTML = [
            '<div class="photo-profile-story__ring">',
            '  <div class="photo-profile-story__ring-inner">',
            '    <img src="' + escapeHtml(imageUrl) + '" alt="' + escapeHtml((story.image && story.image.description) || story.description || story.title || '') + '"/>',
            '  </div>',
            '</div>',
            '<div class="photo-profile-story__label">' + escapeHtml(story.display_time || 'Now') + '</div>'
        ].join('');
        list.insertAdjacentElement('afterbegin', node);
        if (window.feather) {
            window.feather.replace();
        }
    }

    function submitStoryCreateOverlay() {
        var elements = getStoryCreateElements();
        if (!elements.submit || state.storyCreateSubmitting) {
            return;
        }

        var title = elements.titleInput ? String(elements.titleInput.value || '').trim() : '';
        var description = elements.descriptionInput ? String(elements.descriptionInput.value || '').trim() : '';
        if (!title || !description || !state.currentStoryCreateSelection.length) {
            updateStoryCreateSubmitState();
            return;
        }

        state.storyCreateSubmitting = true;
        elements.submit.disabled = true;

        fetch('/' + state.expId + '/api/photo/story/create', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                photo_ids: state.currentStoryCreateSelection,
                title: title,
                description: description
            })
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (result) {
            if (result && result.ok && result.story) {
                insertProfileStory(result.story);
                closeAllOverlays();
            }
        }).catch(function () {
            if (elements.submit) {
                elements.submit.textContent = 'Unable to share';
            }
        }).finally(function () {
            state.storyCreateSubmitting = false;
            updateStoryCreateSubmitState();
        });
    }

    function getShareElements() {
        if (!state.shareOverlay) {
            return {};
        }
        return {
            title: state.shareOverlay.querySelector('[data-photo-share-title]'),
            back: state.shareOverlay.querySelector('[data-photo-share-back]'),
            submit: state.shareOverlay.querySelector('[data-photo-share-submit]'),
            empty: state.shareOverlay.querySelector('[data-photo-share-empty]'),
            editor: state.shareOverlay.querySelector('[data-photo-share-editor]'),
            preview: state.shareOverlay.querySelector('[data-photo-share-preview]'),
            file: state.shareOverlay.querySelector('[data-photo-share-file]'),
            form: state.shareOverlay.querySelector('[data-photo-share-form]'),
            select: state.shareOverlay.querySelector('[data-photo-share-select]'),
            caption: state.shareOverlay.querySelector('[data-photo-share-caption]'),
            altText: state.shareOverlay.querySelector('[data-photo-share-alt]'),
            author: state.shareOverlay.querySelector('[data-photo-share-author]'),
            authorAvatar: state.shareOverlay.querySelector('[data-photo-share-author-avatar]')
        };
    }

    function clearSharePreview() {
        var elements = getShareElements();
        if (state.currentShareObjectUrl && window.URL && window.URL.revokeObjectURL) {
            try {
                window.URL.revokeObjectURL(state.currentShareObjectUrl);
            } catch (error) {
                // Ignore revocation issues.
            }
        }
        state.currentShareObjectUrl = '';
        state.currentShareFile = null;
        state.currentShareSubmitting = false;

        if (elements.file) {
            elements.file.value = '';
        }
        if (elements.preview) {
            elements.preview.removeAttribute('src');
            elements.preview.alt = '';
        }
        if (elements.caption) {
            elements.caption.value = '';
        }
        if (elements.altText) {
            elements.altText.value = '';
        }
    }

    function setShareStage(editorVisible) {
        var elements = getShareElements();
        if (!elements.empty || !elements.editor || !elements.back || !elements.submit) {
            return;
        }

        elements.empty.classList.toggle('is-visible', !editorVisible);
        elements.editor.classList.toggle('is-visible', editorVisible);
        elements.back.hidden = !editorVisible;
        elements.submit.hidden = !editorVisible;
        elements.submit.textContent = 'Share';
        if (elements.title) {
            elements.title.textContent = editorVisible ? 'Add details' : 'Create new post';
        }
    }

    function syncShareAuthor() {
        var elements = getShareElements();
        var sidebar = document.querySelector('.photo-sidebar__profile');
        var avatar = sidebar ? sidebar.querySelector('img') : null;
        var name = sidebar ? sidebar.querySelector('strong') : null;
        if (elements.authorAvatar && avatar) {
            elements.authorAvatar.src = avatar.getAttribute('src') || '';
            elements.authorAvatar.alt = avatar.getAttribute('alt') || '';
        }
        if (elements.author && name) {
            elements.author.textContent = name.textContent || '';
        }
    }

    function openShareOverlay() {
        if (!state.shareOverlay) {
            return;
        }
        clearSharePreview();
        syncShareAuthor();
        setShareStage(false);
        openOverlay(state.shareOverlay);
        bindShareInteractions();
    }

    function showShareFile(file) {
        var elements = getShareElements();
        if (!file || !elements.preview) {
            return;
        }
        if (state.currentShareObjectUrl && window.URL && window.URL.revokeObjectURL) {
            try {
                window.URL.revokeObjectURL(state.currentShareObjectUrl);
            } catch (error) {
                // Ignore revocation issues.
            }
        }
        state.currentShareFile = file;
        state.currentShareObjectUrl = window.URL && window.URL.createObjectURL ? window.URL.createObjectURL(file) : '';
        if (state.currentShareObjectUrl) {
            elements.preview.src = state.currentShareObjectUrl;
        }
        elements.preview.alt = file.name || 'Selected image preview';
        setShareStage(true);
    }

    function insertSharedPostHtml(html) {
        if (!html) {
            return;
        }
        var container = document.getElementById('posts-container');
        if (!container) {
            return;
        }
        container.insertAdjacentHTML('afterbegin', html);
        if (window.YSPhotoInitializeDynamicFeedContent) {
            window.YSPhotoInitializeDynamicFeedContent(container);
        } else if (window.feather) {
            window.feather.replace();
        }
    }

    function submitShareOverlay() {
        var elements = getShareElements();
        if (!elements.file || !elements.form || !state.currentShareFile || state.currentShareSubmitting) {
            return;
        }
        var formData = new FormData();
        formData.append('image', state.currentShareFile);
        formData.append('alt_text', elements.altText ? String(elements.altText.value || '').trim() : '');
        formData.append('caption', elements.caption ? String(elements.caption.value || '').trim() : '');

        state.currentShareSubmitting = true;
        if (elements.submit) {
            elements.submit.disabled = true;
        }

        fetch('/' + state.expId + '/api/photo/share', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (result) {
            if (result && result.ok) {
                insertSharedPostHtml(result.html || '');
                closeAllOverlays();
            }
        }).catch(function () {
            if (elements.submit) {
                elements.submit.textContent = 'Unable to share';
            }
        }).finally(function () {
            state.currentShareSubmitting = false;
            if (elements.submit) {
                elements.submit.disabled = false;
            }
        });
    }

    function postPhotoAction(photoId, action, payload, onSuccess) {
        if (!state.expId || !photoId) {
            return;
        }

        var endpoints = {
            like: '/' + state.expId + '/api/photo/post/' + encodeURIComponent(photoId) + '/like',
            bookmark: '/' + state.expId + '/api/photo/post/' + encodeURIComponent(photoId) + '/bookmark',
            share: '/' + state.expId + '/api/photo/post/' + encodeURIComponent(photoId) + '/share'
        };
        var endpoint = endpoints[action];
        if (!endpoint) {
            return;
        }

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: payload ? JSON.stringify(payload) : '{}'
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (result) {
            if (typeof onSuccess === 'function') {
                onSuccess(result || {});
            }
        }).catch(function () {
            // Silent failure keeps the feed usable.
        });
    }

    function toggleLike(photoId) {
        postPhotoAction(photoId, 'like', null, function (result) {
            var payload = {
                liked: !!result.liked,
                likes: typeof result.likes === 'number' ? result.likes : 0
            };
            updatePostCardCounts(photoId, payload);
        });
    }

    function toggleBookmark(photoId) {
        postPhotoAction(photoId, 'bookmark', null, function (result) {
            var payload = {
                bookmarked: !!result.bookmarked
            };
            updatePostCardCounts(photoId, payload);
        });
    }

    function sharePost(photoId) {
        postPhotoAction(photoId, 'share', null, function (result) {
            if (typeof result.shares === 'number') {
                updatePostCardCounts(photoId, { shares: result.shares });
            }
            if (result && result.html) {
                insertSharedPostHtml(result.html);
            }
        });
    }

    function bindShareInteractions() {
        if (!state.shareOverlay) {
            return;
        }

        var elements = getShareElements();
        if (elements.select && elements.select.getAttribute('data-photo-bound') !== 'true') {
            elements.select.setAttribute('data-photo-bound', 'true');
            elements.select.addEventListener('click', function (event) {
                event.preventDefault();
                if (elements.file) {
                    elements.file.click();
                }
            });
        }

        if (elements.file && elements.file.getAttribute('data-photo-bound') !== 'true') {
            elements.file.setAttribute('data-photo-bound', 'true');
            elements.file.addEventListener('change', function () {
                if (elements.file && elements.file.files && elements.file.files[0]) {
                    showShareFile(elements.file.files[0]);
                }
            });
        }

        if (elements.back && elements.back.getAttribute('data-photo-bound') !== 'true') {
            elements.back.setAttribute('data-photo-bound', 'true');
            elements.back.addEventListener('click', function (event) {
                event.preventDefault();
                clearSharePreview();
                setShareStage(false);
            });
        }

        if (elements.submit && elements.submit.getAttribute('data-photo-bound') !== 'true') {
            elements.submit.setAttribute('data-photo-bound', 'true');
            elements.submit.addEventListener('click', function (event) {
                event.preventDefault();
                submitShareOverlay();
            });
        }

        if (elements.form && elements.form.getAttribute('data-photo-bound') !== 'true') {
            elements.form.setAttribute('data-photo-bound', 'true');
            elements.form.addEventListener('submit', function (event) {
                event.preventDefault();
                submitShareOverlay();
            });
        }

        if (state.shareOverlay && state.shareOverlay.getAttribute('data-photo-bound') !== 'true') {
            state.shareOverlay.setAttribute('data-photo-bound', 'true');
            state.shareOverlay.addEventListener('dragover', function (event) {
                event.preventDefault();
            });
            state.shareOverlay.addEventListener('drop', function (event) {
                event.preventDefault();
                var files = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files : [];
                if (files && files.length) {
                    showShareFile(files[0]);
                }
            });
        }
    }

    function removeStoryTrigger(trigger) {
        if (!trigger || !trigger.parentNode) {
            return;
        }
        var parent = trigger.parentNode;
        trigger.remove();
        if (!parent.querySelector('[data-photo-open-story]')) {
            var empty = parent.querySelector('.photo-feed-stories__empty');
            if (!empty) {
                empty = document.createElement('div');
                empty.className = 'notification is-light photo-feed-stories__empty';
                empty.textContent = 'No story previews are available yet.';
                parent.appendChild(empty);
            }
        }
    }

    function renderPostOverlay(payload) {
        if (!state.postOverlay || !payload || !payload.post) {
            return;
        }

        var post = payload.post;
        state.currentPhotoId = String(post.photo_id || post.id || '').trim();
        state.currentPost = post;
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
            var authorHref = post.author_href || '';
            var authorName = escapeHtml(post.author || '');
            author.innerHTML = authorHref
                ? '<a class="photo-inline-link" href="' + escapeHtml(authorHref) + '">' + authorName + '</a>'
                : authorName;
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
            var captionAuthorHref = post.author_href || '';
            var captionAuthor = escapeHtml(post.author || '');
            var captionBody = post.post_html || escapeHtml(post.post || '');
            caption.innerHTML = '<strong>' + (captionAuthorHref ? '<a class="photo-inline-link" href="' + escapeHtml(captionAuthorHref) + '">' + captionAuthor + '</a>' : captionAuthor) + '</strong> ' + captionBody;
        }
        if (commentsList) {
            commentsList.innerHTML = renderCommentTree(post.comments_list || []);
            bindCommentInteractions(commentsList);
        }

        syncPostOverlayState(state.currentPhotoId, {
            likes: post.likes || 0,
            comments: post.comments || 0,
            shares: post.shares || 0,
            liked_by_label: post.liked_by_label || ''
        });

        bindComposerInteractions();

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

    function openStoryOverlay(storyId, trigger) {
        var story = findStoryById(storyId);
        if (!story) {
            return;
        }
        var targetTrigger = trigger || null;
        var context = getContext();
        var endpoint = context.expId && story.story_id
            ? '/' + context.expId + '/api/photo/story/' + encodeURIComponent(story.story_id) + '/view'
            : '';
        if (!endpoint) {
            renderStoryOverlay(story);
            return;
        }

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (result) {
            if (result && result.ok) {
                if (typeof result.view_count === 'number') {
                    story.view_count = result.view_count;
                }
                renderStoryOverlay(story);
                if (targetTrigger && targetTrigger.getAttribute('data-photo-story-remove-on-open') === 'true') {
                    removeStoryTrigger(targetTrigger);
                }
                return;
            }
            renderStoryOverlay(story);
        }).catch(function () {
            renderStoryOverlay(story);
        });
    }

    function bindEvents() {
        document.addEventListener('click', function (event) {
            var shareTrigger = event.target.closest('[data-photo-open-share]');
            if (shareTrigger) {
                event.preventDefault();
                openShareOverlay();
                return;
            }

            var storyCreateTrigger = event.target.closest('[data-photo-open-story-create]');
            if (storyCreateTrigger) {
                event.preventDefault();
                openStoryCreateOverlay();
                return;
            }

            var profileEditTrigger = event.target.closest('[data-photo-open-profile-edit]');
            if (profileEditTrigger) {
                event.preventDefault();
                openProfileEditOverlay();
                return;
            }

            var likeTrigger = event.target.closest('[data-photo-post-like]');
            if (likeTrigger) {
                event.preventDefault();
                toggleLike(likeTrigger.getAttribute('data-photo-post-id'));
                return;
            }

            var bookmarkTrigger = event.target.closest('[data-photo-post-bookmark]');
            if (bookmarkTrigger) {
                event.preventDefault();
                toggleBookmark(bookmarkTrigger.getAttribute('data-photo-post-id'));
                return;
            }

            var sharePostTrigger = event.target.closest('[data-photo-post-share]');
            if (sharePostTrigger) {
                event.preventDefault();
                sharePost(sharePostTrigger.getAttribute('data-photo-post-id'));
                return;
            }

            var storyTrigger = event.target.closest('[data-photo-open-story]');
            if (storyTrigger) {
                event.preventDefault();
                openStoryOverlay(storyTrigger.getAttribute('data-photo-open-story'), storyTrigger);
                return;
            }

            var storyCreatePhotoTrigger = event.target.closest('[data-photo-story-create-photo]');
            if (storyCreatePhotoTrigger) {
                event.preventDefault();
                toggleStoryCreatePhoto(storyCreatePhotoTrigger.getAttribute('data-photo-story-create-photo'));
                return;
            }

            var profileAvatarTrigger = event.target.closest('[data-photo-profile-edit-avatar-option]');
            if (profileAvatarTrigger) {
                event.preventDefault();
                setProfileEditSelection(profileAvatarTrigger.getAttribute('data-photo-profile-edit-avatar-option'));
                return;
            }

            var profileUploadTrigger = event.target.closest('[data-photo-profile-edit-upload-trigger]');
            if (profileUploadTrigger) {
                event.preventDefault();
                var uploadInput = state.profileEditOverlay ? state.profileEditOverlay.querySelector('[data-photo-profile-edit-upload]') : null;
                if (uploadInput) {
                    uploadInput.click();
                }
                return;
            }

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

            if (event.target.matches('[data-photo-post-overlay]') ||
                event.target.matches('[data-photo-people-overlay]') ||
                event.target.matches('[data-photo-story-overlay]') ||
                event.target.matches('[data-photo-story-create-overlay]') ||
                event.target.matches('[data-photo-profile-edit-overlay]')) {
                closeAllOverlays();
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeAllOverlays();
                return;
            }
            if (!state.storyOverlay || !state.storyOverlay.classList.contains('is-open')) {
                return;
            }
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                state.currentStoryIndex -= 1;
                updateStoryCarousel();
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                state.currentStoryIndex += 1;
                updateStoryCarousel();
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

        if (state.storyOverlay) {
            var prev = state.storyOverlay.querySelector('[data-photo-story-prev]');
            var next = state.storyOverlay.querySelector('[data-photo-story-next]');
            if (prev) {
                prev.addEventListener('click', function (event) {
                    event.preventDefault();
                    state.currentStoryIndex -= 1;
                    updateStoryCarousel();
                });
            }
            if (next) {
                next.addEventListener('click', function (event) {
                    event.preventDefault();
                    state.currentStoryIndex += 1;
                    updateStoryCarousel();
                });
            }
        }

        if (state.storyCreateOverlay) {
            var storyCreateSubmit = state.storyCreateOverlay.querySelector('[data-photo-story-create-submit]');
            var storyCreateTitle = state.storyCreateOverlay.querySelector('[data-photo-story-create-input-title]');
            var storyCreateDescription = state.storyCreateOverlay.querySelector('[data-photo-story-create-input-description]');
            var storyCreateForm = state.storyCreateOverlay.querySelector('[data-photo-story-create-form]');
            if (storyCreateSubmit && storyCreateSubmit.getAttribute('data-photo-bound') !== 'true') {
                storyCreateSubmit.setAttribute('data-photo-bound', 'true');
                storyCreateSubmit.addEventListener('click', function (event) {
                    event.preventDefault();
                    submitStoryCreateOverlay();
                });
            }
            if (storyCreateTitle && storyCreateTitle.getAttribute('data-photo-bound') !== 'true') {
                storyCreateTitle.setAttribute('data-photo-bound', 'true');
                storyCreateTitle.addEventListener('input', updateStoryCreateSubmitState);
            }
            if (storyCreateDescription && storyCreateDescription.getAttribute('data-photo-bound') !== 'true') {
                storyCreateDescription.setAttribute('data-photo-bound', 'true');
                storyCreateDescription.addEventListener('input', updateStoryCreateSubmitState);
            }
            if (storyCreateForm && storyCreateForm.getAttribute('data-photo-bound') !== 'true') {
                storyCreateForm.setAttribute('data-photo-bound', 'true');
                storyCreateForm.addEventListener('submit', function (event) {
                    event.preventDefault();
                    submitStoryCreateOverlay();
                });
            }
            if (state.storyCreateOverlay.getAttribute('data-photo-bound') !== 'true') {
                state.storyCreateOverlay.setAttribute('data-photo-bound', 'true');
                state.storyCreateOverlay.addEventListener('dragover', function (event) {
                    event.preventDefault();
                });
            }
        }

        if (state.profileEditOverlay) {
            var profileEditSubmit = state.profileEditOverlay.querySelector('[data-photo-profile-edit-submit]');
            var profileEditForm = state.profileEditOverlay.querySelector('[data-photo-profile-edit-form]');
            var profileEditUpload = state.profileEditOverlay.querySelector('[data-photo-profile-edit-upload]');
            if (profileEditSubmit && profileEditSubmit.getAttribute('data-photo-bound') !== 'true') {
                profileEditSubmit.setAttribute('data-photo-bound', 'true');
                profileEditSubmit.addEventListener('click', function (event) {
                    event.preventDefault();
                    submitProfileEditOverlay();
                });
            }
            if (profileEditForm && profileEditForm.getAttribute('data-photo-bound') !== 'true') {
                profileEditForm.setAttribute('data-photo-bound', 'true');
                profileEditForm.addEventListener('submit', function (event) {
                    event.preventDefault();
                    submitProfileEditOverlay();
                });
            }
            if (profileEditUpload && profileEditUpload.getAttribute('data-photo-bound') !== 'true') {
                profileEditUpload.setAttribute('data-photo-bound', 'true');
                profileEditUpload.addEventListener('change', function () {
                    var file = profileEditUpload.files && profileEditUpload.files[0] ? profileEditUpload.files[0] : null;
                    handleProfileEditUpload(file);
                    profileEditUpload.value = '';
                });
            }
        }
    }

    function init() {
        var context = getContext();
        state.expId = String(context.expId || '');
        state.loggedId = String(context.loggedId || context.userId || '');
        state.storyGalleryItems = Array.isArray(context.storyGalleryItems) ? context.storyGalleryItems.slice() : [];
        if (!ensureOverlayElements()) {
            return;
        }
        window.YSPhotoOpenPost = openPostOverlay;
        window.YSPhotoOpenPeople = openPeopleOverlay;
        window.YSPhotoOpenStory = openStoryOverlay;
        bindEvents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
