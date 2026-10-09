// Sets the "Current local time" value shown in the sidebar user card
// (microblogging/components/sidebar_user_card.html). Extracted from an
// inline <script> as part of the ongoing Phase T6 inline-script reduction
// effort -- this logic has no server-side (Jinja) data dependency, so it
// moves to a static file with no data-bridge needed.
(function () {
    var target = document.getElementById("sidebar-current-date");
    if (target) {
        target.textContent = new Date().toLocaleString();
    }
})();
