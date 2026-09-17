/*! popovers-pages.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Handles the pages popovers that appear when hovering a page avatar
========================================================================== */

'use strict'

function getPagesPopovers() {
  $('*[data-page-popover]').each(function () {
    var e = $(this)
    var pageRef = $(this).attr('data-page-popover')

    var messageIcon = feather.icons.mail.toSvg()
    var profileIcon = feather.icons['more-horizontal'].toSvg()
    var pinIcon = feather.icons['map-pin'].toSvg()
    var usersIcon = feather.icons.users.toSvg()
    var tagIcon = feather.icons.tag.toSvg()
    var bookmarkIcon = feather.icons.bookmark.toSvg()

    $.ajax({
      url: 'assets/data/api/pages/pages.json',
      async: true,
      dataType: 'json',
      success: function (data) {
        e.webuiPopover({
          trigger: 'hover',
          placement: 'auto',
          width: 300,
          padding: false,
          offsetLeft: 0,
          offsetTop: 20,
          animation: 'pop',
          cache: false,
          content: function () {
            var destroyLoader = setTimeout(function () {
              $('.loader-overlay').removeClass('is-active')
            }, 1000)

            var html = `
                            <div class="profile-popover-block">

                                <div class="loader-overlay is-active">
                                    <div class="loader is-loading"></div>
                                </div>

                                <div class="profile-popover-wrapper">
                                    <div class="popover-cover">
                                        <img src="${data[pageRef].cover_image}">
                                        <div class="popover-avatar">
                                            <img class="avatar" src="${data[pageRef].profile_picture}">
                                        </div>
                                    </div>
                                    <div class="popover-meta">
                                        <span class="page-meta">
                                            <span class="pagename">${data[pageRef].name}</span>
                                        </span>
                                        <div class="page-activity">
                                            ${tagIcon}
                                            <div class="text">
                                                ${data[pageRef].activity}
                                            </div>
                                        </div>
                                        <div class="page-followers">
                                            ${usersIcon}
                                            <div class="text">
                                                <a href="#">${data[pageRef].followers}</a> Followers
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="popover-actions">
                                    <a href="#" class="popover-icon">
                                        ${profileIcon}
                                    </a>
                                    <a href="#" class="popover-icon">
                                        ${bookmarkIcon}
                                    </a>
                                    <a href="#" class="popover-icon">
                                        ${messageIcon}
                                    </a>
                                </div>
                            </div>
                        `

            return html
            return destroyLoader
          },
        })
      },
    })
  })
}

$(function () {
  /* Pages

        0. Fast Pizza
        1. Lonely Droid
        2. Meta Movies
        3. Nuclearjs
        4. Slicer
        5. Css Ninja
        6. Brent University
        8. Los Angeles
        9. Lipflow
        10. Drop Cosmetics
        11. Quick Fashion
        13. Go Pizza
        14. O' Reilly's
        15. Epic Burger
        16. Downtown Subs
    */

  getPagesPopovers()
})
