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
            'startMiscellaneaTutorial',
            'startExternalRuntimesTutorial',
            'startExternalRuntimeDetailTutorial',
            'startPluginTutorial',
            'startClientsAdhocTutorial',
            'startAgentsDashboardTutorial',
            'startGenericAdminTutorial'
        ];

        var hasTutorial = tutorialFunctions.some(function(fn) {
            return typeof window[fn] === 'function';
        });

        var tutorialBtn = document.getElementById('tutorial-replay-btn');
        if (!tutorialBtn) {
            return;
        }

        if (hasTutorial) {
            tutorialBtn.classList.remove('d-none');
            tutorialBtn.style.display = 'inline-flex';
        } else {
            tutorialBtn.classList.add('d-none');
            tutorialBtn.style.display = 'none';
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
    } else if (typeof window.startExternalRuntimesTutorial === 'function') {
        window.startExternalRuntimesTutorial();
    } else if (typeof window.startExternalRuntimeDetailTutorial === 'function') {
        window.startExternalRuntimeDetailTutorial();
    } else if (typeof window.startPluginTutorial === 'function') {
        // tutorial supplied by a plugin page (Training, Scenario Design, ...)
        window.startPluginTutorial();
    } else if (typeof window.startClientsAdhocTutorial === 'function') {
        window.startClientsAdhocTutorial();
    } else if (typeof window.startAgentsDashboardTutorial === 'function') {
        window.startAgentsDashboardTutorial();
    } else if (typeof window.startGenericAdminTutorial === 'function') {
        window.startGenericAdminTutorial();
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

function renderDownloadNotifications(items, unreadCount, avatars) {
    var list = document.getElementById('download-notifications-list');
    var badge = document.getElementById('download-notifications-badge');
    if (!list || !badge) {
        return;
    }

    var avatarsActive = !!(avatars && avatars.status && avatars.status !== 'ready');
    if (unreadCount > 0 || avatarsActive) {
        badge.classList.remove('d-none');
        badge.style.display = 'inline-flex';
        badge.textContent = unreadCount > 0
            ? (unreadCount > 99 ? '99+' : String(unreadCount))
            : '\u2193';  // arrow: only the background download is running
    } else {
        badge.classList.add('d-none');
        badge.style.display = 'none';
    }

    var rows = [];
    if (avatarsActive) {
        var pct = avatars.percent || 0;
        rows.push(
            '<a class="dropdown-item download-notification-item download-item-unread" href="/admin/notifications">' +
            '<div class="download-notification-title">' + escapeHtml(avatars.title) + '</div>' +
            '<div class="download-notification-meta"><span class="tag is-info is-light">' + escapeHtml(avatars.label) + '</span> ' +
            (avatars.status === 'idle' ? '' : pct + '%') + '</div>' +
            (avatars.status === 'idle' ? '' : '<progress class="progress is-info is-small" value="' + pct + '" max="100" style="margin:.4rem 0 0"></progress>') +
            '</a>'
        );
    }
    if (!items || items.length === 0) {
        if (!avatarsActive) {
            rows.push('<div class="dropdown-item">' + YI18n.t('No notifications yet.') + '</div>');
        }
    } else {
        items.slice(0, 5).forEach(function(item) {
            var statusTagClass =
                item.status === 'ready'
                    ? 'is-success'
                    : (item.status === 'failed' ? 'is-danger' : (item.status === 'processing' ? 'is-info' : 'is-light'));
            var unreadClass = item.is_read ? '' : ' download-item-unread';
            var action = item.action_url
                ? '<a class="download-notification-link" href="' + item.action_url + '">' + YI18n.t('Download') + '</a>'
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
                '<span class="tag ' + statusTagClass + '">' + escapeHtml(item.status_label || item.status) + '</span>' +
                action +
                '</div>' +
                '<div class="download-notification-message">' + escapeHtml(item.message) + '</div>' +
                (item.progress && item.status === 'processing'
                    ? '<progress class="progress is-info is-small" value="' + item.progress.percent + '" max="100" style="margin:.4rem 0 0"></progress>'
                    : '') +
                relatedHtml +
                '</div>'
            );
        });
    }

    rows.push('<hr class="dropdown-divider">');
    rows.push('<a class="dropdown-item has-text-weight-semibold" href="/admin/notifications">' + YI18n.t('See all') + '</a>');
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
        var avatars = null;
        try {
            var ar = await fetch('/admin/avatars/status', { credentials: 'same-origin' });
            if (ar.ok) { avatars = await ar.json(); }
        } catch (e) { /* the bell works without it */ }
        renderDownloadNotifications(payload.items || [], payload.unread_count || 0, avatars);
        // poll faster while the profile pictures are being downloaded
        var jobRunning = (payload.items || []).some(function(it) { return it.status === 'processing' && it.progress; });
        var active = jobRunning || !!(avatars && avatars.status && avatars.status !== 'ready');
        if (active !== window.__ysAvatarsFast) {
            window.__ysAvatarsFast = active;
            if (window.__ysNotifTimer) { clearInterval(window.__ysNotifTimer); }
            window.__ysNotifTimer = setInterval(refreshDownloadNotifications, active ? 5000 : 30000);
        }
    } catch (error) {
        console.error('Failed to refresh download notifications:', error);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    refreshDownloadNotifications();
    window.__ysNotifTimer = setInterval(refreshDownloadNotifications, 30000);
    document.addEventListener('ys-notifications-refresh', function() {
        refreshDownloadNotifications();
    });

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
