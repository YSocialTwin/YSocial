/*! popovers-users.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Handles the user popovers that appear when hovering a user image
========================================================================== */

'use strict'

function getUserPopovers() {
  $('*[data-user-popover]').each(function () {
    var e = $(this)
    var userRef = $(this).attr('data-user-popover')

    var messageIcon = feather.icons['message-circle'].toSvg()
    var profileIcon = feather.icons['more-horizontal'].toSvg()
    var pinIcon = feather.icons['map-pin'].toSvg()
    var usersIcon = feather.icons.users.toSvg()
    var bookmarkIcon = feather.icons.bookmark.toSvg()

    $.ajax({
      url: 'assets/data/api/users/users.json',
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
                                            <img src="${data[userRef].cover_image}">
                                            <div class="popover-avatar">
                                                <img class="avatar" src="${data[userRef].profile_picture}">
                                            </div>
                                        </div>

                                        <div class="popover-meta">
                                            <span class="user-meta">
                                                <span class="username">${data[userRef].first_name} ${data[userRef].last_name}</span>
                                            </span>
                                            <!--span class="job-title">${data[userRef].title}</span-->
                                            <div class="common-friends">
                                                ${usersIcon}
                                                <div class="text">
                                                    ${data[userRef].common_friends} mutual friend(s)
                                                </div>
                                            </div>
                                            <div class="user-location">
                                                ${pinIcon}
                                                <div class="text">
                                                    From <a href="#">${data[userRef].location}</a>
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
  /* Users

        0. Jenna Davis
        1. Dan Walker
        2. Stella Bergmann
        3. Daniel Wellington
        4. David Kim
        5. Edward Mayers
        6. Elise Walker
        7. Milly Augustine
        8. Bobby Brown
        9. Nelly Schwartz
        10. Lana Henrikssen
        11. Gaelle Morris
        12. Mike Lasalle
        13. Rolf Krupp
        14. Ken Rogers
        15. Leana Marks
        16. Aline Cambell
        17. Mike Donovan
        18. George A. Romero
        19. Brian Stevenson
        20. Azzouz El Paytoun
        21. Cathy Smith
        22. Bob Barker
        23. Greg Patel
        24. Hisashi Yokida
    */

  getUserPopovers()
})
