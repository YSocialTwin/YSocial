/*! main.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Main js file
========================================================================== */

'use strict'

//Set environment variable (Used for development)

/* 
    Possible values:
    1. development
    2. ''
*/

var env = 'development'

//Pageloader
initPageloader()

$(function () {
  if (env === 'development') {
    //Demo images
    changeDemoHrefs()

    //Demo hrefs
    changeDemoImages()
  }

  //Lazy Load
  const el = document.querySelectorAll('[data-lazy-load]')
  const observer = lozad(el, {
    loaded: function (el) {
      // Custom implementation on a loaded element
      el.parentNode.classList.add('loaded')
    },
  })

  observer.observe()

  //Demo links
  $('.demo-link a').on('click', function (e) {
    e.preventDefault()
    var theme = $(this).closest('.demo-link').attr('data-theme')
    window.localStorage.setItem('theme', theme)
    var href = $(this).attr('href')

    window.open(href)
  })

  //Toggle Dark mode
  toggleTheme()

  //Code highlight init
  $('.highlight-block code').each(function (i, block) {
    hljs.highlightBlock(block)
  })

  //Init navbar v1
  initNavbar()

  //Init navbar v2
  initNavbarV2()

  //Init sidebar v1
  initSidebarV1()

  //Dashboard
  linkCheck()

  //Mobile menu toggle
  initResponsiveMenu()

  //Navbar dropdown
  initNavDropdowns()

  //Navbar Cart
  initNavbarCart()

  //Common Dropdown
  initDropdowns()

  //Tabs
  initTabs()

  //Modals
  initModals()

  //Attribute background images
  initBgImages()

  //Feather icons initialization
  feather.replace()

  //Emojis
  initEmojiPicker()

  initLightboxEmojis()

  //Video Embed
  initVideoEmbed()

  //Load More
  initLoadMore()

  //Init tooltips
  initTooltips()

  //Init Like Button
  initLikeButton()

  //Init Simple Popover
  initSimplePopover()

  //Share modal demo
  initShareModal()

  //Users autocomplete
  initUsersAutocomplete()

  //Init Tipuedrop
  initSuggestionSearch()
})
