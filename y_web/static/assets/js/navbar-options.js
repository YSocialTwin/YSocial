/*! navbar-options.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Navbar options js file
========================================================================== */

'use strict'

//Options nav subsearch
function initSubSearch() {
  //Toggle comments
  if ($('#show-subsearch, #hide-subsearch').length) {
    $('#show-subsearch, #hide-subsearch').on('click', function () {
      $('#show-subsearch, #hide-subsearch, #subsearch').toggleClass('is-hidden')
      $('#subsearch input').focus()
    })
  }
}

//Options nav subsearch
function initSidebar() {
  //Toggle sidebar
  if ($('#show-filters, #hide-filters').length) {
    $('#show-filters, #hide-filters').on('click', function () {
      $('#show-filters, #hide-filters').toggleClass('is-hidden')
      $('.filters-panel').toggleClass('is-active')
      $('.main-container').toggleClass('has-sidebar')
    })
  }
}

$(function () {
  //Subnavbar search
  initSubSearch()

  //Sidebars
  initSidebar()
})
