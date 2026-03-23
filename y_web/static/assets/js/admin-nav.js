/*
 * admin-nav.js
 *
 * Navigation helper functions for the YSocial admin dashboard.
 * Extracted from admin/dash_head.html as part of Phase T3b of
 * TEMPLATE_SEPARATION_REFACTORING.md.
 *
 * Loaded once via admin/footer.html; covers all 35+ admin pages.
 */

// ---------------------------------------------------------------------------
// External-URL / Blog-banner helpers  (extracted from admin/dash_head.html)
// ---------------------------------------------------------------------------

/**
 * Open an external URL in the system's default browser.
 * This function works in both regular browser mode and PyInstaller desktop mode.
 *
 * @param {Event} event - The click event (to prevent default link behavior)
 * @param {string} url - The URL to open
 */
function openExternalUrl(event, url) {
    event.preventDefault();

    // Try using the backend endpoint first (works in PyInstaller mode)
    fetch('/admin/open_external_url', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ url: url })
    }).then(function(response) {
        if (!response.ok) {
            // Fallback to window.open if backend fails (e.g., in regular browser mode)
            console.log('Backend open_external_url failed, falling back to window.open');
            window.open(url, '_blank');
        }
    }).catch(function(error) {
        console.error('Error opening external URL:', error);
        // Fallback to window.open on network error
        window.open(url, '_blank');
    });
}

function markBlogPostAsRead(event, postId, link) {
    // Prevent default link behavior
    event.preventDefault();

    // Mark blog post as read when link is clicked
    fetch('/admin/mark_blog_post_read/' + postId, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    }).then(function(response) {
        if (response.ok) {
            // Hide the banner
            document.getElementById('blog-banner').style.display = 'none';
        } else {
            console.error('Failed to mark blog post as read:', response.status);
        }
        // Open the link after marking as read (or even if marking failed)
        openExternalUrl(event, link);
    }).catch(function(error) {
        console.error('Error marking blog post as read:', error);
        // Still open the link even if marking failed
        openExternalUrl(event, link);
    });
}

function dismissBlogPost(postId) {
    // Mark blog post as read when dismissed
    fetch('/admin/mark_blog_post_read/' + postId, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    }).then(function(response) {
        if (response.ok) {
            document.getElementById('blog-banner').style.display = 'none';
        } else {
            console.error('Failed to dismiss blog post:', response.status);
        }
    }).catch(function(error) {
        console.error('Error dismissing blog post:', error);
    });
}

// ---------------------------------------------------------------------------
// Tutorial button detector  (extracted from admin/dash_head.html)
// ---------------------------------------------------------------------------

// Show tutorial button only if a tutorial exists for this page
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for tutorial scripts to register their functions
    setTimeout(function() {
        // Check for any available tutorial functions
        var tutorialFunctions = [
            'startExpDetailsTutorial',
            'startExperimentsTutorial',
            'startDashboardTutorial',
            'startAgentsTutorial',
            'startPopulationsTutorial',
            'startUsersTutorial',
            'startClientsTutorial',
            'startPagesTutorial',
            'startClientDetailsTutorial',
            'startUserDetailsTutorial',
            'startMiscellaneaTutorial'
        ];

        var hasTutorial = tutorialFunctions.some(function(fn) {
            return typeof window[fn] === 'function';
        });

        if (hasTutorial) {
            document.getElementById('tutorial-replay-btn').style.display = 'inline-flex';
        }
    }, 1500);
});

function replayPageTutorial() {
    // Call the appropriate tutorial function based on what's available
    if (typeof window.startExpDetailsTutorial === 'function') {
        window.startExpDetailsTutorial();
    } else if (typeof window.startExperimentsTutorial === 'function') {
        window.startExperimentsTutorial();
    } else if (typeof window.startDashboardTutorial === 'function') {
        window.startDashboardTutorial();
    } else if (typeof window.startAgentsTutorial === 'function') {
        window.startAgentsTutorial();
    } else if (typeof window.startPopulationsTutorial === 'function') {
        window.startPopulationsTutorial();
    } else if (typeof window.startUsersTutorial === 'function') {
        window.startUsersTutorial();
    } else if (typeof window.startClientsTutorial === 'function') {
        window.startClientsTutorial();
    } else if (typeof window.startPagesTutorial === 'function') {
        window.startPagesTutorial();
    } else if (typeof window.startClientDetailsTutorial === 'function') {
        window.startClientDetailsTutorial();
    } else if (typeof window.startUserDetailsTutorial === 'function') {
        window.startUserDetailsTutorial();
    } else if (typeof window.startMiscellaneaTutorial === 'function') {
        window.startMiscellaneaTutorial();
    }
}

// ---------------------------------------------------------------------------
// Download notifications + toolbar menus  (extracted from admin/dash_head.html)
// ---------------------------------------------------------------------------

function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderDownloadNotifications(items, unreadCount) {
    var list = document.getElementById('download-notifications-list');
    var badge = document.getElementById('download-notifications-badge');
    if (!list || !badge) {
        return;
    }

    if (unreadCount > 0) {
        badge.style.display = 'inline-flex';
        badge.textContent = unreadCount > 99 ? '99+' : String(unreadCount);
    } else {
        badge.style.display = 'none';
    }

    var rows = [];
    if (!items || items.length === 0) {
        rows.push('<div class="dropdown-item">No notifications yet.</div>');
    } else {
        items.slice(0, 5).forEach(function(item) {
            var statusTagClass =
                item.status === 'ready'
                    ? 'is-success'
                    : (item.status === 'failed' ? 'is-danger' : (item.status === 'processing' ? 'is-info' : 'is-light'));
            var unreadClass = item.is_read ? '' : ' download-item-unread';
            var action = item.action_url
                ? '<a class="download-notification-link" href="' + item.action_url + '">Open</a>'
                : '';
            var relatedHtml = '';
            if (item.related_experiments && item.related_experiments.length > 0) {
                var firstExp = item.related_experiments[0];
                var extraCount = item.related_experiments.length - 1;
                var moreLabel = extraCount > 0 ? ' <span class="download-related-more">+' + extraCount + '</span>' : '';
                relatedHtml =
                    '<div class="download-notification-related">' +
                    '<a class="download-notification-link" href="' + firstExp.url + '">' + escapeHtml(firstExp.name) + '</a>' + moreLabel +
                    '</div>';
            }
            rows.push(
                '<div class="dropdown-item download-notification-item' + unreadClass + '">' +
                '<div class="download-notification-title">' + escapeHtml(item.title) + '</div>' +
                '<div class="download-notification-meta">' +
                '<span class="tag ' + statusTagClass + '">' + escapeHtml(item.status) + '</span>' +
                action +
                '</div>' +
                '<div class="download-notification-message">' + escapeHtml(item.message) + '</div>' +
                relatedHtml +
                '</div>'
            );
        });
    }

    rows.push('<hr class="dropdown-divider">');
    rows.push('<a class="dropdown-item has-text-weight-semibold" href="/admin/notifications">See all</a>');
    list.innerHTML = rows.join('');
}

async function refreshDownloadNotifications() {
    try {
        var response = await fetch('/admin/notifications/data?limit=5', {
            credentials: 'same-origin'
        });
        if (!response.ok) {
            return;
        }
        var payload = await response.json();
        renderDownloadNotifications(payload.items || [], payload.unread_count || 0);
    } catch (error) {
        console.error('Failed to refresh download notifications:', error);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    refreshDownloadNotifications();
    setInterval(refreshDownloadNotifications, 15000);

    var menus = document.querySelectorAll('.dashboard-toolbar .header-buttons .toolbar-menu');
    menus.forEach(function(menu) {
        var trigger = menu.querySelector('.dropdown-trigger > button');
        var panel = menu.querySelector('.dropdown-menu');
        if (!trigger || !panel) { return; }

        trigger.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();
            var shouldOpen = !menu.classList.contains('is-active');
            menus.forEach(function(m) { m.classList.remove('is-active'); });
            if (shouldOpen) {
                menu.classList.add('is-active');
            }
        });

        panel.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    });

    document.addEventListener('click', function() {
        menus.forEach(function(m) { m.classList.remove('is-active'); });
    });

    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            menus.forEach(function(m) { m.classList.remove('is-active'); });
        }
    });
});
