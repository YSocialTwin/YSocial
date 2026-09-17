var ForumProfile = (function() {
window.redditProfileToggleDropdown = function(event, trigger) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!trigger) {
        return false;
    }
    document.querySelectorAll('#posts-container .dropdown-trigger.is-active').forEach(function(node) {
        if (node !== trigger) {
            node.classList.remove('is-active');
        }
    });
    trigger.classList.toggle('is-active');
    return false;
};

window.redditProfileDeletePost = function(event, trigger) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    var postId = trigger && trigger.getAttribute ? trigger.getAttribute('data-post-id') : '';
    if (!postId || !window.RedditApi) {
        return false;
    }
    if (!window.confirm('Delete this post? This action cannot be undone.')) {
        return false;
    }
    window.RedditApi.deletePost(postId)
        .then(function() {
            var card = trigger.closest('[data-reddit-post]');
            if (card) {
                card.remove();
            }
        })
        .fail(function(err) {
            window.alert((err && err.message) || 'Unable to delete post right now.');
        });
    return false;
};

document.addEventListener('DOMContentLoaded', function() {
    var postsContainer = document.getElementById('posts-container');

    function initialsForName(name) {
        var cleaned = String(name || '').trim();
        if (!cleaned) {
            return 'U';
        }
        var parts = cleaned.split(/\s+/).filter(Boolean).slice(0, 2);
        return parts.map(function(part) { return part.charAt(0).toUpperCase(); }).join('') || 'U';
    }

    function colorForName(name) {
        var palette = ['#0f766e', '#0369a1', '#1d4ed8', '#6d28d9', '#be123c', '#b45309', '#15803d', '#334155'];
        var source = String(name || 'user');
        var hash = 0;
        for (var i = 0; i < source.length; i += 1) {
            hash = ((hash << 5) - hash) + source.charCodeAt(i);
            hash |= 0;
        }
        return palette[Math.abs(hash) % palette.length];
    }

    function buildLocalAvatar(name) {
        var initials = initialsForName(name);
        var fill = colorForName(name);
        var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">' +
            '<rect width="80" height="80" rx="40" fill="' + fill + '"/>' +
            '<text x="50%" y="52%" dominant-baseline="middle" text-anchor="middle"' +
            ' font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#ffffff">' + initials + '</text>' +
            '</svg>';
        return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
    }

    function resolvedProfileImage(img) {
        var configured = (img.getAttribute('data-demo-src') || '').trim();
        if (configured && !configured.includes('via.placeholder.com')) {
            return configured;
        }
        return buildLocalAvatar(img.getAttribute('data-author-name') || img.getAttribute('alt') || 'User');
    }

    function hydrateProfileImages(root) {
        var scope = root || postsContainer;
        if (!scope) return;
        scope.querySelectorAll('[data-demo-src]').forEach(function(img) {
            var newSrc = resolvedProfileImage(img);
            img.setAttribute('src', newSrc);
            img.onerror = function() {
                img.onerror = null;
                img.setAttribute('src', buildLocalAvatar(img.getAttribute('data-author-name') || img.getAttribute('alt') || 'User'));
            };
        });
        if (window.feather && window.feather.replace) {
            window.feather.replace();
        }
    }

    hydrateProfileImages(postsContainer);

    document.addEventListener('click', function(event) {
        var trigger = event.target.closest('.dropdown-trigger');
        if (!trigger || !postsContainer || !postsContainer.contains(trigger)) {
            document.querySelectorAll('#posts-container .dropdown-trigger.is-active').forEach(function(node) {
                node.classList.remove('is-active');
            });
        }
    });

    if (window.InfiniteScroll) {
        var config = window.YS_DATA_FORUM_PROFILE || {};
        InfiniteScroll.init({
            apiEndpoint: '/' + (config.expId || '') + '/api/profile/' + (config.userId || '') + '/' + (config.mode || 'new'),
            postsContainerId: 'posts-container',
            initialPage: config.page || 1
        });
    }
});

    return {
        toggleDropdown: window.redditProfileToggleDropdown,
        deletePost: window.redditProfileDeletePost
    };
})();
