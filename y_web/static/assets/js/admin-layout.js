/*
 * admin-layout.js
 *
 * Layout behaviour for the YSocial admin dashboard.
 * Extracted from admin/head.html as part of Phase T3a of
 * TEMPLATE_SEPARATION_REFACTORING.md.
 *
 * Loaded once via admin/footer.html; covers all 35+ admin pages.
 *
 * Requires: jQuery (loaded earlier in the page)
 */

// ---------------------------------------------------------------------------
// Alert dismissal  (extracted from admin/head.html)
// ---------------------------------------------------------------------------
$(document).ready(function() {
    // Handle alert dismissal without page refresh
    $(document).on('click', '[data-dismiss="alert"]', function(e) {
        e.preventDefault();
        $(this).closest('.alert').fadeOut(300, function() {
            $(this).remove();
        });
    });
});

// ---------------------------------------------------------------------------
// Sidebar toggle  (extracted from admin/head.html)
// ---------------------------------------------------------------------------
function toggleSidebar() {
    var sidebar = document.getElementById('dashboard-sidebar');
    var overlay = document.getElementById('sidebar-overlay');

    if (sidebar.classList.contains('open')) {
        closeSidebar();
    } else {
        sidebar.classList.add('open');
        overlay.classList.add('active');
    }
}

function closeSidebar() {
    var sidebar = document.getElementById('dashboard-sidebar');
    var overlay = document.getElementById('sidebar-overlay');

    sidebar.classList.remove('open');
    overlay.classList.remove('active');
}

// Close sidebar when clicking on a link (for mobile) -- a group toggle is
// not real navigation (it just expands/collapses its submenu), so it's
// excluded here and handled by its own listener below instead.
document.addEventListener('DOMContentLoaded', function() {
    var sidebarLinks = document.querySelectorAll('.dashboard-aside-link');
    sidebarLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            if (link.classList.contains('dashboard-aside-group-toggle')) {
                return;
            }
            if (window.innerWidth <= 768) {
                closeSidebar();
            }
        });
    });
});

// ---------------------------------------------------------------------------
// Two-level sidebar groups (Experiments / Extensions / Administration)
//
// Desktop: a group's submenu opens as a flyout card next to its icon (see
// core.css). Mobile: the same markup becomes an in-place accordion (see
// admin-responsive.css, max-width:768px). Only one group is kept open at a
// time, it closes on an outside click or Escape, and the group containing
// the current page is auto-expanded with its link highlighted on load.
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
    var groups = document.querySelectorAll('.dashboard-aside-group');
    if (!groups.length) {
        return;
    }

    function closeGroup(group) {
        group.classList.remove('is-open');
        var toggle = group.querySelector('.dashboard-aside-group-toggle');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
        }
    }

    function openGroup(group) {
        group.classList.add('is-open');
        var toggle = group.querySelector('.dashboard-aside-group-toggle');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'true');
        }
    }

    groups.forEach(function (group) {
        var toggle = group.querySelector('.dashboard-aside-group-toggle');
        if (!toggle) {
            return;
        }
        toggle.addEventListener('click', function (event) {
            event.preventDefault();
            var alreadyOpen = group.classList.contains('is-open');
            groups.forEach(closeGroup);
            if (!alreadyOpen) {
                openGroup(group);
            }
        });
    });

    document.addEventListener('click', function (event) {
        groups.forEach(function (group) {
            if (!group.contains(event.target)) {
                closeGroup(group);
            }
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            groups.forEach(closeGroup);
        }
    });

    // Highlight the current page's link and auto-expand its group, if any.
    var currentPath = window.location.pathname.replace(/\/$/, '');
    document.querySelectorAll('.dashboard-aside-link').forEach(function (link) {
        var href = link.getAttribute('href') || '';
        var linkPath = href.split('?')[0].replace(/\/$/, '');
        if (linkPath && linkPath === currentPath) {
            link.classList.add('is-active');
            var parentGroup = link.closest('.dashboard-aside-group');
            if (parentGroup) {
                openGroup(parentGroup);
            }
        }
    });
});
