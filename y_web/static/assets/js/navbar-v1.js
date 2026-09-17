/*! navbar-v1.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Navbar v1 js file
========================================================================== */

'use strict'

function initNavbar() {
  $(window).on('scroll', function () {
    var height = $(window).scrollTop()
    if (height > 65) {
      if ($('.options-nav').length) {
        $('.navbar').addClass('no-shadow')
        $('.options-nav').removeClass('no-shadow')
      } else {
        $('.navbar').removeClass('no-shadow')
        if ($('.navbar.is-landing').length) {
          $('.navbar').removeClass('no-background')
        }
      }
    } else {
      if ($('.options-nav').length) {
        $('.navbar').addClass('no-shadow')
        $('.options-nav').addClass('no-shadow')
      } else {
        $('.navbar').addClass('no-shadow')
        if ($('.navbar.is-landing').length) {
          $('.navbar').addClass('no-background')
        }
      }
    }
  })

  //Clear navbar search input
  $('#clear-search').on('click', function () {
    $(this).siblings('input').val('')
  })
}

$(function () {})
