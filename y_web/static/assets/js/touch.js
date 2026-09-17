/*! touch.js | Friendkit | 2019-2020 */

/* ==========================================================================
Touch functions
========================================================================== */

$(function () {
  'use strict'
  ;(function (factory) {
    if (typeof define === 'function' && define.amd) {
      define(['jquery', 'hammerjs'], factory)
    } else if (typeof exports === 'object') {
      factory(require('jquery'), require('hammerjs'))
    } else {
      factory(jQuery, Hammer)
    }
  })(function ($, Hammer) {
    function hammerify(el, options) {
      var $el = $(el)
      if (!$el.data('hammer')) {
        $el.data('hammer', new Hammer($el[0], options))
      }
    }

    $.fn.hammer = function (options) {
      return this.each(function () {
        hammerify(this, options)
      })
    }

    // extend the emit method to also trigger jQuery events
    Hammer.Manager.prototype.emit = (function (originalEmit) {
      return function (type, data) {
        originalEmit.call(this, type, data)
        $(this.element).trigger({
          type: type,
          gesture: data,
        })
      }
    })(Hammer.Manager.prototype.emit)
  })

  //Videos
  var videoHammer

  function closeTouchVideoSidebar() {
    // Get a reference to an element.
    var videoWrapper = document.querySelector('.videos-wrapper')

    // Create an instance of Hammer with the reference.
    videoHammer = new Hammer(videoWrapper)

    // Subscribe to a quick start event: press, tap, or doubletap.
    // For a full list of quick start events, read the documentation.
    videoHammer.on('swipeleft', function () {
      console.log('Swipe left detected.')
      $('.videos-wrapper').find('.videos-sidebar').removeClass('is-active')
    })

    videoHammer.on('swiperight', function () {
      console.log('Swipe right detected.')
      $('.videos-wrapper').find('.videos-sidebar').addClass('is-active')
      $('.videos-wrapper').find('.related-side').removeClass('is-opened')
    })
  }

  if ($('.videos-sidebar').length) {
    if (window.matchMedia('(max-width: 767px)').matches) {
      closeTouchVideoSidebar()
    } else if (window.matchMedia('(max-width: 768px)').matches) {
      if (window.matchMedia('(orientation: portrait)').matches) {
        closeTouchVideoSidebar()
      } else {
        if (videoHammer !== undefined) {
          videoHammer.destroy()
        }
      }
    } else {
      if (videoHammer !== undefined) {
        videoHammer.destroy()
      }
    }

    $(window).on('resize', function () {
      if (window.matchMedia('(max-width: 767px)').matches) {
        closeTouchVideoSidebar()
      } else if (window.matchMedia('(max-width: 768px)').matches) {
        if (window.matchMedia('(orientation: portrait)').matches) {
          closeTouchVideoSidebar()
        } else {
          if (videoHammer !== undefined) {
            videoHammer.destroy()
          }
        }
      } else {
        if (videoHammer !== undefined) {
          videoHammer.destroy()
        }
      }
    })
  }
})
