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

// Close sidebar when clicking on a link (for mobile)
document.addEventListener('DOMContentLoaded', function() {
    var sidebarLinks = document.querySelectorAll('.dashboard-aside-link');
    sidebarLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 768) {
                closeSidebar();
            }
        });
    });
});
