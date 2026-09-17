/*! friends.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Friends page js file
========================================================================== */

$(function () {
  'use strict'

  if ($('#friends-page').length) {
    //Hide loader
    $('.subloader').removeClass('is-active')

    //Init combo box
    initComboBox()

    //Init image combo box
    initImageComboBox()

    //Enable full text search function
    function enableSearch() {
      $('.friend-card').addClass('textFilter-target')
      $('.friend-card')
        .find(' .friend-info h3,  .friend-info p')
        .addClass('textFilter-match')
    }

    enableSearch()

    //Init search filter
    initTextFilter()

    //Friend menu tabs
    $('.option-tabs.is-friends .option-tab').on('click', function () {
      callLoader(800)
      var targetTab = $(this).attr('data-tab')
      $(this).siblings('.option-tab').removeClass('is-active')
      $(this).addClass('is-active')
      setTimeout(function () {
        $('.card-row-wrap').removeClass('is-active')
        $('#' + targetTab).addClass('is-active')
      }, 200)
    })

    //Star a friend
    $('.star-friend').on('click', function () {
      $(this).toggleClass('is-active')
    })

    //Call loader
    function callLoader(t) {
      $('.subloader').addClass('is-active')
      setTimeout(function () {
        $('.subloader').removeClass('is-active')
      }, t)
    }
  }
})
