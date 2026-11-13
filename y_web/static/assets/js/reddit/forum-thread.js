/* Thread view helpers: comment collapse and "Join the conversation" composer trigger. */
(function () {
    "use strict";
    document.addEventListener("click", function (ev) {
        var collapse = ev.target.closest(".fr-collapse");
        if (collapse) {
            var branch = collapse.closest(".fr-branch");
            var collapsed = branch.classList.toggle("is-collapsed");
            collapse.setAttribute("aria-expanded", collapsed ? "false" : "true");
            var icon = collapse.querySelector("i");
            if (icon) {
                icon.className = collapsed ? "mdi mdi-plus-circle-outline" : "mdi mdi-minus-circle-outline";
            }
            return;
        }
        var join = ev.target.closest(".fr-join-conversation");
        if (join) {
            var target = join.getAttribute("data-reply-target");
            var btn = document.querySelector('.toggle-reply-button[data-reply-target="' + target + '"]');
            if (btn) {
                btn.click();
            }
        }
    });
})();
