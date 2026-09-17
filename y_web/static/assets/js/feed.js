/*! feed.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Feed page js file
========================================================================== */

$(function () {
  'use strict'

  if ($('#activity-feed').length) {
    //Feed v1 left menu
    if ($('.feed-menu-v1').length) {
      $('.feed-menu-v1 .main-menu li.is-active').find('.submenu').slideDown()
      $('.feed-menu-v1 .main-menu li').on('click', function () {
        //$('.submenu').slideUp();
        $(this)
          .siblings('li')
          .removeClass('is-active')
          .find('.submenu')
          .slideUp()
        $(this).addClass('is-active').find('.submenu').slideDown()
      })
    }
  }

  if ($('#share-modal').length) {
    //Share modal main dropdown
    $('.share-dropdown').on('click', function () {
      $(this).toggleClass('is-active')
    })

    //Share modal main dropdown
    $('.share-dropdown .dropdown-item').on('click', function () {
      var targetSharingChannel = $(this).attr('data-target-channel')
      var channelIcon = $(this).find('i').attr('class')
      var channelName = $(this).find('h3').text()

      if (targetSharingChannel !== undefined) {
        $('.share-dropdown .button')
          .find('i')
          .removeClass()
          .addClass(channelIcon)
        $('.share-dropdown .button').find('span').text(channelName)
        $('.share-channel-control').addClass('is-hidden')
        $('.footer-action.is-active').removeClass('is-active')
        $('#share-to-' + targetSharingChannel)
          .removeClass('is-hidden')
          .find('input')
          .focus()
      }
    })

    //Share modal page selector subdropdown
    $('.page-dropdown').on('click', function () {
      $(this).toggleClass('is-active')
    })

    //Share modal footer actions
    $('.action-wrap .footer-action').on('click', function () {
      var targetAction = $(this).attr('data-target-action')

      $('.footer-action.is-active').removeClass('is-active')
      $(this).addClass('is-active')

      if (targetAction !== undefined) {
        //$('.share-channel-control').addClass('is-hidden');
        $('.bottom-share-inputs .field').addClass('is-hidden')
        $('#action-' + targetAction)
          .removeClass('is-hidden')
          .find('input')
          .focus()
      }
    })
  }

  if ($('.feed-slider-wrapper').length) {
    $('.feed-slider-inner').slick({
      centerMode: true,
      centerPadding: '10px',
      slidesToShow: 3,
      prevArrow:
        "<div class='slick-custom is-prev'><i class='mdi mdi-chevron-left'></i></div>",
      nextArrow:
        "<div class='slick-custom is-next'><i class='mdi mdi-chevron-right'></i></div>",
      responsive: [
        {
          breakpoint: 768,
          settings: {
            arrows: false,
            centerMode: true,
            centerPadding: '40px',
            slidesToShow: 3,
          },
        },
        {
          breakpoint: 480,
          settings: {
            arrows: false,
            centerMode: true,
            centerPadding: '40px',
            slidesToShow: 1,
          },
        },
      ],
    })
  }
})
