/*! navbar-mobile.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Navbar mobile js file
========================================================================== */

'use strict'

function initNavbarV2() {
  if ($('.navbar-v2').length) {
    $('#open-mobile-search, .mobile-search .close-icon').on(
      'click',
      function () {
        $('.mobile-search .input').val('')
        $('.top-nav')
          .find('.left, .right, .mobile-search')
          .toggleClass('is-hidden')
        $('.mobile-search .input').focus()
      },
    )

    // Get current page URL
    var url = window.location.href

    // remove # from URL
    url = url.substring(
      0,
      url.indexOf('#') == -1 ? url.length : url.indexOf('#'),
    )

    // remove parameters from URL
    url = url.substring(
      0,
      url.indexOf('?') == -1 ? url.length : url.indexOf('?'),
    )

    // select file name
    url = url.substr(url.lastIndexOf('/') + 1)

    // If file name not available
    if (url == '') {
      url = 'index.html'
    }

    $('.sub-nav li').removeClass('is-active')

    // Loop all menu items
    $('.sub-nav a').each(function () {
      // select href
      var href = $(this).attr('href')

      // Check filename
      if (url == href) {
        // Add active class
        $(this).closest('li').addClass('is-active')
      }
    })
  }
}

$(function () {})
