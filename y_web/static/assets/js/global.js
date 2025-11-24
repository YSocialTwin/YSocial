/*! global.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Project wide reusable functions
========================================================================== */

'use strict'

/* ==========================================================================
Utility / Demo
========================================================================== */

//Change demo images
function changeDemoImages() {
  $('*[data-demo-src]').each(function () {
    var newSrc = $(this).attr('data-demo-src')
    $(this).attr('src', newSrc)
  })

  $('*[data-demo-background]').each(function () {
    var newBg = $(this).attr('data-demo-background')
    $(this).attr('data-background', newBg)
  })
}

//Change demo hrefs
function changeDemoHrefs() {
  $('*[data-demo-href]').each(function () {
    var newHref = $(this).attr('data-demo-href')
    $(this).attr('href', newHref)
  })
}

//Init attribute background images
function initBgImages() {
  if ($('.has-background-image').length) {
    $('.has-background-image').each(function () {
      var bgImage = $(this).attr('data-background')
      if (bgImage !== undefined) {
        $(this).css('background-image', 'url(' + bgImage + ')')
      }
    })
  }
}

/**
 * Open an external URL in the system's default browser.
 * This function works in both regular browser mode and PyInstaller desktop mode.
 * 
 * @param {Event} event - The click event (to prevent default link behavior)
 * @param {string} url - The URL to open
 */
function openExternalUrl(event, url) {
    event.preventDefault();
    
    // Try using the backend endpoint first (works in PyInstaller mode)
    fetch('/admin/open_external_url', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ url: url })
    }).then(function(response) {
        if (!response.ok) {
            // Fallback to window.open if backend fails (e.g., in regular browser mode)
            console.log('Backend open_external_url failed, falling back to window.open');
            window.open(url, '_blank');
        }
    }).catch(function(error) {
        console.error('Error opening external URL:', error);
        // Fallback to window.open on network error
        window.open(url, '_blank');
    });
}

/* ==========================================================================
Dark mode
========================================================================== */

//Get Theme
function setThemeToLocalStorage(value) {
  window.localStorage.setItem('theme', value)
  if (!$('#friendkit-demo-landing').length) {
    if (value === 'dark') {
      $('body').addClass('is-dark')
    } else {
      $('body').removeClass('is-dark')
    }
  }
}

function toggleTheme() {
  var theme = window.localStorage.getItem('theme')
  console.log(theme)
  if (theme != null && theme != undefined) {
    setThemeToLocalStorage(theme)

    if (theme === 'dark') {
      $('.theme-toggle input').prop('checked', true)
    }

    $(document).trigger('themeChange', theme)
  }

  $('.theme-toggle input').on('change', function () {
    if ($(this).prop('checked') === true) {
      console.log('checked')
      setThemeToLocalStorage('dark')
      $('.theme-toggle input').prop('checked', true)
      $(document).trigger('themeChange', 'dark')
    } else {
      setThemeToLocalStorage('light')
      $('.theme-toggle input').prop('checked', false)
      $(document).trigger('themeChange', 'light')
    }
  })
}

function linkCheck() {
  if ($('.dashboard-aside-link').length) {
    $('.dashboard-aside-link').each(function () {
      if ($(this).prop('href') == window.location.href) {
        $(this).addClass('is-active')
      }
    })
  }
}

/* ==========================================================================
Pageloader
========================================================================== */

function initPageloader() {
  if ($('.pageloader').length) {
    $('.pageloader').toggleClass('is-active')

    $(window).on('load', function () {
      var pageloaderTimeout = setTimeout(function () {
        $('.pageloader').toggleClass('is-active')
        $('.infraloader').toggleClass('is-active')
        clearTimeout(pageloaderTimeout)
      }, 700)
      //Placeloaders
      if ($('#main-feed').length) {
        var shadowDomTimeout = setTimeout(function () {
          $('#shadow-dom').remove()
          $('.true-dom').removeClass('is-hidden')
          clearTimeout(shadowDomTimeout)
        }, 2500)
      }
      if ($('.questions-wrap').length) {
        var shadowDomTimeout = setTimeout(function () {
          $(
            '#questions-shadow-dom-settings, #questions-shadow-dom-single, #questions-shadow-dom-home, #questions-shadow-dom-stats, #questions-shadow-dom-categories',
          ).remove()
          $('.true-dom').removeClass('is-hidden')
          clearTimeout(shadowDomTimeout)
        }, 2500)
      }
    })
  }
}

/* ==========================================================================
UI Elements
========================================================================== */

//init tipue search
function initSuggestionSearch() {
  $('#tipue_drop_input, #tipue_drop_input_mobile').tipuedrop()
}

//Init nav/toolbar dropdowns
function initNavDropdowns() {
  $('.drop-trigger').click(function () {
    $('.nav-drop').removeClass('is-active')
    $(this).find('.nav-drop').addClass('is-active')
    if ($(this).hasClass('is-account')) {
      $(this).addClass('is-opened')
    }
  })

  $(document).click(function (e) {
    var target = e.target
    if (
      !$(target).is('.nav-drop') &&
      !$(target).parents().is('.drop-trigger')
    ) {
      $('.nav-drop').removeClass('is-active')
      $('.is-account').removeClass('is-opened')
    }
  })
}

//Init Cart dropdown
function initNavbarCart() {
  $('.is-cart .cart-button').on('click', function () {
    $(this).closest('.is-cart').find('.shopping-cart').addClass('is-active')
    setTimeout(function () {
      $('.navbar-cart-loader').removeClass('is-active')
    }, 800)
  })

  $(document).click(function (e) {
    var target = e.target
    if (
      !$(target).is('.is-cart .cart-button') &&
      !$(target).parents().is('.is-cart')
    ) {
      $('.shopping-cart').removeClass('is-active')
      setTimeout(function () {
        $('.navbar-cart-loader').addClass('is-active')
      }, 300)
    }
  })
}

//Init dropdowns
function initDropdowns() {
  $('.dropdown-trigger').click(function () {
    $('.dropdown-trigger').removeClass('is-active')
    $(this).addClass('is-active')
  })

  $(document).click(function (e) {
    var target = e.target
    if (
      !$(target).is('.dropdown-trigger img') &&
      !$(target).parents().is('.dropdown-trigger')
    ) {
      $('.dropdown-trigger').removeClass('is-active')
    }
  })
}

//Init tabs
function initTabs() {
  $('.nav-tabs-wrapper ul li').on('click', function () {
    var tab_id = $(this).attr('data-tab')

    $(this).siblings('li').removeClass('is-active')
    $(this)
      .closest('.nav-tabs-wrapper')
      .children('.tab-content')
      .removeClass('is-active')

    $(this).addClass('is-active')
    $('#' + tab_id).addClass('is-active')
  })
}

//Init modals
function initModals() {
  if ($('.modal-trigger').length) {
    $('.modal-trigger').on('click', function () {
      var modalID = $(this).attr('data-modal')
      $('#' + modalID).toggleClass('is-active')
    })

    $('.modal-close, .close-modal').on('click', function () {
      $('.modal.is-active').removeClass('is-active')
    })
  }
}

//Init Emojis
function initEmojiPicker() {
  var id = 0
  $('.post-comment.has-emojis').each(function () {
    id = id + 1
    var $this = $(this)
    var wrapper = $this.find('.card-footer')
    var textarea = $this.find('textarea')
    var action = $this.find('.is-emoji')

    wrapper.attr('id', 'post-comment-wrapper-' + id)
    textarea.attr('id', 'post-comment-textarea-' + id)
    action.attr('id', 'post-comment-button-' + id)

    const container = document.getElementById('post-comment-wrapper-' + id)
    const messageInput = document.getElementById('post-comment-textarea-' + id)
    const button = document.getElementById('post-comment-button-' + id)

    const picker = new EmojiButton({
      position: 'top-end',
      rootElement: container,
      autoHide: false,
    })

    picker.on('emoji', (emoji) => {
      messageInput.value += emoji
      messageInput.dispatchEvent(new Event('keyup'))
    })

    button.addEventListener('click', () => {
      picker.pickerVisible ? picker.hidePicker() : picker.showPicker(button)
    })
  })
}

function initLightboxEmojis() {
  var id = 0
  $('.has-lightbox-emojis').each(function () {
    id = id + 1
    var $this = $(this)
    var wrapper = $this.find('.controls-inner')
    var textarea = $this.find('textarea')
    var action = $this.find('.emoji-button')

    wrapper.attr('id', 'lightbox-post-comment-wrapper-' + id)
    textarea.attr('id', 'lightbox-post-comment-textarea-' + id)
    action.attr('id', 'lightbox-post-comment-button-' + id)

    const container = document.getElementById(
      'lightbox-post-comment-wrapper-' + id,
    )
    const messageInput = document.getElementById(
      'lightbox-post-comment-textarea-' + id,
    )
    const button = document.getElementById('lightbox-post-comment-button-' + id)

    const picker = new EmojiButton({
      position: 'top-end',
      rootElement: container,
      autoHide: false,
    })

    picker.on('emoji', (emoji) => {
      messageInput.value += emoji
      messageInput.dispatchEvent(new Event('keyup'))
    })

    button.addEventListener('click', () => {
      picker.pickerVisible ? picker.hidePicker() : picker.showPicker(button)
    })
  })
}

//Video Embed
function initVideoEmbed() {
  if ($('#video-embed').length) {
    embedVideo('#video-embed')
  }
}

//Init Like button
function initLikeButton() {
  $('.like-button').on('click', function () {
    $(this).toggleClass('is-active')
  })
}

//Load more buttons
function initLoadMore() {
  var t
  $('.load-more-button').on('click', function (e) {
    e.preventDefault()
    clearTimeout(t)
    $(this).toggleClass('loading')
    t = setTimeout(function () {
      $('.load-more-button').removeClass('loading')
    }, 2500)
  })
}

//Post Comment sections toggling
function initPostComments() {
  $('.fab-wrapper.is-comment, .close-comments').on('click', function (e) {
    $(this)
      .addClass('is-active')
      .closest('.card')
      .find('.content-wrap, .comments-wrap')
      .toggleClass('is-hidden')
    var jump = $(this).closest('.is-post')
    var new_position = $(jump).offset()
    console.log(new_position)
    $('html, body')
      .stop()
      .animate({ scrollTop: new_position.top - 70 }, 500)
    e.preventDefault()
    setTimeout(function () {
      $('.emojionearea-editor').val('')
    }, 400)
  })
}

//Simple popover
function initSimplePopover() {
  $('.has-tip').webuiPopover({
    trigger: 'hover',
    placement: 'auto',
    width: 300,
    padding: false,
    offsetLeft: 0,
    offsetTop: 0,
    animation: 'pop',
    cache: false,
  })
}

//Tooltips
function initTooltips() {
  $('.has-tooltip').ggtooltip({
    html: true,
    textcolor: '#fff',
    backcolor: '#444',
    bordercolor: '#444',
  })
}

/* ==========================================================================
Combo boxes
========================================================================== */

function initUsersAutocomplete() {
  //Friends autocomplete
  if ($('#users-autocpl').length) {
    var html = ''

    var summary = ''

    var usersOptions = {
      url: 'assets/data/api/users/user-autocpl.json',
      getValue: 'name',
      template: {
        type: 'custom',
        method: function (value, item) {
          return (
            '<div class=' +
            'template-wrapper' +
            '><div class=' +
            'avatar-wrapper' +
            '>' +
            '<img class=' +
            'autocpl-avatar' +
            " src='" +
            item.pic +
            "' /><img class=" +
            'avatar-badge' +
            " src='" +
            item.badge +
            "' /></div><div class=" +
            'entry-text' +
            '>' +
            value +
            '<br><span>' +
            item.location +
            '</span></div></div> '
          )
        },
      },
      highlightPhrase: false,
      list: {
        maxNumberOfElements: 5,
        showAnimation: {
          type: 'fade', //normal|slide|fade
          time: 400,
          callback: function () {},
        },
        match: {
          enabled: true,
        },
        onChooseEvent: function () {
          //Get the user name from the autocomplete
          var newRecipient = $('#users-autocpl').val()
          //empty the input for next use
          $('#users-autocpl').val('')

          html = `
                        <div class="control tag-control">
                            <div class="tags has-addons">
                                <a class="tag is-link">${newRecipient}</a>
                                <a class="tag is-delete is-inverted"></a>
                            </div>
                        </div>
                    `

          summary = `
                        <span class="tagged-friend"><small>&mdash; with</small> <a class="is-inverted" href="#">${newRecipient}</a>,</span>
                    `

          //Append tag template in list
          $.when($('#tag-list').append(html)).done(function () {
            //Add the name to the tagged friends summary
            $('#options-summary').append(summary)
            //Make added tag removable
            $('.tag.is-delete').on('click', function () {
              var friendName = $(this)
                .closest('.tags')
                .find('.tag.is-link')
                .text()
              $(this).closest('.tag-control').remove()
              $('.tagged-friend a').each(function () {
                var comparedName = $(this).text()
                if (friendName === comparedName) {
                  $(this).closest('.tagged-friend').remove()
                } else {
                  return false
                }
              })
            })
          })
        },
      },
    }

    $('#users-autocpl').easyAutocomplete(usersOptions)
  }
}

//Init custom select
function initKSelect() {
  //Custom select
  $('.custom-select').on('click', function () {
    $(this).toggleClass('is-active')
  })
  $(document).click(function (e) {
    var target = e.target
    if (
      !$(target).is('.custom-select') &&
      !$(target).parents().is('.control')
    ) {
      $('.custom-select').removeClass('is-active')
    }
  })
  $('.custom-select input').on('change', function () {
    var selectedValue = $(this).siblings('.option-meta').find('span').text()
    $(this)
      .closest('.custom-select')
      .find('.select-box span')
      .html(selectedValue)
  })
}

//Init Combo boxes
function initComboBox() {
  $('.is-combo .combo-box').on('click', function () {
    $(this).toggleClass('is-active')
  })

  $('.combo-box .box-dropdown li').on('click', function (e) {
    var target = e.target
    //Get selected item data
    var itemIconClass = $(this).find('.item-icon i').attr('class')
    var itemIcon = $(this).find('.item-icon i')
    var itemIconClass = $(this).find('.item-icon i').attr('class')
    var itemSvgIcon = $(this).find('.item-icon').html()
    var itemName = $(this).find('.item-name').text()
    var iconTemplate = '<i class="' + itemIconClass + '"></i>'
    var template = ''

    console.log(itemSvgIcon)

    if (
      !$(target).is('.box-dropdown li, body') &&
      !$(target).parents().is('.box-dropdown')
    ) {
      $('.box-dropdown').removeClass('is-active')
    }
    if ($(target).is('body')) {
      $('.box-dropdown').removeClass('is-active')
    }

    //Handle dropdown item active state toggle
    $(this).siblings('li.is-active').removeClass('is-active')
    $(this).addClass('is-active')
    //Update combo box selected value
    if (itemIcon.length) {
      $(this).closest('.combo-box').find('.combo-item i').remove()
      $(this).closest('.combo-box').find('.combo-item svg').remove()
      $(this).closest('.combo-box').find('.combo-item').prepend(iconTemplate)
      $(this)
        .closest('.combo-box')
        .find('.combo-item .selected-item')
        .text(itemName)
    } else {
      $(this).closest('.combo-box').find('.combo-item i').remove()
      $(this).closest('.combo-box').find('.combo-item').prepend(itemSvgIcon)
      $(this)
        .closest('.combo-box')
        .find('.combo-item .selected-item')
        .text(itemName)
    }
  })

  $(document).click(function (e) {
    var target = e.target
    if (!$(target).is('.combo-box') && !$(target).parents().is('.is-combo')) {
      $('.combo-box').removeClass('is-active')
    }
  })
}

//Init Combo boxes
function initImageComboBox() {
  $('.is-combo .image-combo-box').on('click', function () {
    $(this).toggleClass('is-active')
  })

  $('.image-combo-box .box-dropdown li').on('click', function (e) {
    var target = e.target
    //Get selected item data
    var itemPic = $(this).find('.item-icon img').attr('src')
    var itemName = $(this).find('.item-name').text()

    if (
      !$(target).is('.box-dropdown li, body') &&
      !$(target).parents().is('.box-dropdown')
    ) {
      $('.box-dropdown').removeClass('is-active')
    }
    if ($(target).is('body')) {
      $('.box-dropdown').removeClass('is-active')
    }

    //Handle dropdown item active state toggle
    $(this).siblings('li.is-active').removeClass('is-active')
    $(this).addClass('is-active')
    //Update combo box selected value
    $(this)
      .closest('.image-combo-box')
      .find('.combo-item img')
      .attr('src', itemPic)
    $(this)
      .closest('.image-combo-box')
      .find('.combo-item .selected-item')
      .text(itemName)
  })

  $(document).click(function (e) {
    var target = e.target
    if (
      !$(target).is('.image-combo-box') &&
      !$(target).parents().is('.is-combo')
    ) {
      $('.image-combo-box').removeClass('is-active')
    }
  })
}

//Init Combo boxes
function initUserComboBox() {
  $('.is-combo .user-combo-box').on('click', function () {
    $(this).toggleClass('is-active')
  })

  $('.user-combo-box .box-dropdown li').on('click', function (e) {
    var target = e.target
    //Get selected item data
    var itemPic = $(this).find('.item-icon .avatar').attr('src')
    var itemBadge = $(this).find('.item-icon .badge').attr('src')
    var itemName = $(this).find('.item-name').text()

    if (
      !$(target).is('.box-dropdown li, body') &&
      !$(target).parents().is('.box-dropdown')
    ) {
      $('.box-dropdown').removeClass('is-active')
    }
    if ($(target).is('body')) {
      $('.box-dropdown').removeClass('is-active')
    }

    //Handle dropdown item active state toggle
    $(this).siblings('li.is-active').removeClass('is-active')
    $(this).addClass('is-active')
    //Update combo box selected value
    $(this)
      .closest('.user-combo-box')
      .find('.combo-item .avatar')
      .attr('src', itemPic)
    $(this)
      .closest('.user-combo-box')
      .find('.combo-item .badge')
      .attr('src', itemBadge)
    $(this)
      .closest('.user-combo-box')
      .find('.combo-item .selected-item')
      .text(itemName)
  })
}

//Init Combo boxes
function initStackedComboBox() {
  $('.is-combo .stacked-combo-box').on('click', function () {
    $(this).toggleClass('is-active')
  })

  $('.stacked-combo-box .box-dropdown li').on('click', function (e) {
    var target = e.target
    //Get selected item data
    var itemPic = $(this).find('.item-icon img').attr('src')
    var itemName = $(this).find('.item-name').text()
    var itemRef = $(this).attr('data-skill')
    var initialText = 'Select one or more skills'

    var skillTemplate = `
            <img id="${itemRef}" class="is-stacked" src="${itemPic}">
        `

    if (
      !$(target).is('.box-dropdown li, body') &&
      !$(target).parents().is('.box-dropdown')
    ) {
      $('.box-dropdown').removeClass('is-active')
    }
    if ($(target).is('body')) {
      $('.box-dropdown').removeClass('is-active')
    }

    //Handle dropdown item active state toggle
    $(this).toggleClass('is-active')
    console.log(skillTemplate)

    if ($('.stacked-combo-box li.is-active').length == 0) {
      $('#' + itemRef).remove()
      $('#skill-placeholder').removeClass('is-hidden')
      $(this)
        .closest('.stacked-combo-box')
        .find('.selected-item')
        .text(initialText)
    } else {
      $('#skill-placeholder').addClass('is-hidden')
      $(this).closest('.stacked-combo-box').find('.selected-item').text('')
      if ($('#' + itemRef).length) {
        $('#' + itemRef).remove()
      } else {
        $(this)
          .closest('.stacked-combo-box')
          .find('.combo-item')
          .prepend(skillTemplate)
      }
    }
  })
}

//Init Big Combo boxes
function initBigComboBox() {
  $('.big-combo-box').on('click', function () {
    $(this).toggleClass('is-active')
  })

  $('.big-combo-box .box-dropdown li').on('click', function (e) {
    var target = e.target
    //Get selected item data
    var itemIcon = $(this).find('.item-icon i').attr('class')
    var itemName = $(this).find('.item-name span:first-child').text()
    var itemDesc = $(this).find('.item-name span:nth-child(2)').text()

    if (
      !$(target).is('.box-dropdown li, body') &&
      !$(target).parents().is('.box-dropdown')
    ) {
      $('.box-dropdown').removeClass('is-active')
    }
    if ($(target).is('body')) {
      $('.box-dropdown').removeClass('is-active')
    }

    //Handle dropdown item active state toggle
    $(this).siblings('li.is-active').removeClass('is-active')
    $(this).addClass('is-active')
    //Update combo box selected value
    $(this)
      .closest('.big-combo-box')
      .find('.combo-item i')
      .attr('class', itemIcon)
    $(this)
      .closest('.big-combo-box')
      .find('.combo-item .selected-item')
      .text(itemName)
    $(this)
      .closest('.big-combo-box')
      .find('.combo-item .selected-desc')
      .text(itemDesc)
  })
}

/* ==========================================================================
Text filter search
========================================================================== */

//Init text filter
function initTextFilter() {
  ;(function () {
    var defaultText = $('.textFilter-input').val()

    $('.textFilter-input')
      .focus(function (e) {
        if ($(this).val() === defaultText) $(this).val('')
      })
      .blur(function (e) {
        if ($(this).val() === '') $(this).val(defaultText)
      })
      .keyup(function (e) {
        var patterns = $(this).val().toLowerCase().split(' ')
        if (!patterns.length) return
        $('.textFilter-target')
          .hide()
          .removeClass('is-match')
          .addClass('is-not-match')
          .filter(function () {
            var matchText = $(this)
              .find('.textFilter-match')
              .text()
              .toLowerCase()
            for (var i = 0; i < patterns.length; i++)
              if (matchText.indexOf(patterns[i]) === -1) return false
            return true
          })
          .show()
          .removeClass('is-not-match')
          .addClass('is-match')
        //Friends
        if ($('#friends-page').length) {
          var cardCount = $('.card-row-wrap.is-active').find(
            '.friend-card.is-match',
          ).length
          console.log(cardCount)
          if (cardCount == 0) {
            $('.card-row-wrap.is-active')
              .find('.card-row')
              .addClass('is-hidden')
            $('.card-row-wrap.is-active')
              .find('.card-row-placeholder')
              .removeClass('is-hidden')
          } else {
            $('.card-row-wrap.is-active')
              .find('.card-row-placeholder')
              .addClass('is-hidden')
            $('.card-row-wrap.is-active')
              .find('.card-row')
              .removeClass('is-hidden')
          }
        }
      })
  })()
}

/* ==========================================================================
Global Modals
========================================================================== */

//Init share modal demo
function initShareModal() {
  $('.small-fab.share-fab').on('click', function () {
    var $this = $(this)
    var postImage = $this
      .closest('.is-post')
      .find('.post-image img')
      .attr('src')
    var postUser = $this
      .closest('.is-post')
      .find('.user-block .image img')
      .attr('src')
    var postText = $this.closest('.is-post').find('.post-text > p').html()
    if (postImage !== undefined) {
      $('#share-modal-image').attr('src', postImage).removeClass('is-hidden')
    } else {
      $('#share-modal-image').addClass('is-hidden')
    }
    $('#share-modal-avatar').attr('src', postUser)
    $('#share-modal-text').html(postText)
  })
}

//Init About Page slider
function initAboutGlider() {
  $('.about-glider').each(function () {
    if ($(this).is(':visible')) {
      var element = $(this).attr('id')
      new Glider(document.querySelector('#' + element), {
        slidesToShow: 3,
        slidesToScroll: 3,
        dots: '#slider-dots-' + element,
        draggable: true,
        responsive: [
          {
            // screens greater than >= 775px
            breakpoint: 768,
            settings: {
              // Set to `auto` and provide item width to adjust to viewport
              slidesToShow: 3,
              slidesToScroll: 3,
              itemWidth: 150,
              duration: 0.25,
            },
          },
          {
            // screens greater than >= 1024px
            breakpoint: 300,
            settings: {
              slidesToShow: 1,
              slidesToScroll: 1,
              //itemWidth: 150,
              duration: 0.25,
            },
          },
        ],
      })
    }
  })
}

/* ==========================================================================
Toast Sercice
========================================================================== */

var toasts = {}

toasts.service = {
  info: function (title, icon, message, position, t) {
    iziToast.show({
      class: 'toast',
      icon: icon,
      title: title,
      message: message,
      titleColor: '#fff',
      messageColor: '#fff',
      iconColor: '#fff',
      backgroundColor: '#0062ff',
      progressBarColor: '#bc7aff',
      position: position,
      transitionIn: 'fadeInDown',
      close: false,
      timeout: t,
      zindex: 99999,
    })
  },
  success: function (title, icon, message, position, t) {
    iziToast.show({
      class: 'toast',
      icon: icon,
      title: title,
      message: message,
      titleColor: '#fff',
      messageColor: '#fff',
      iconColor: '#fff',
      backgroundColor: '#0062ff',
      progressBarColor: '#fafafa',
      position: position,
      transitionIn: 'fadeInDown',
      close: false,
      timeout: t,
      zindex: 99999,
    })
  },
  error: function (title, icon, message, position, t) {
    iziToast.show({
      class: 'toast',
      icon: icon,
      title: title,
      message: message,
      titleColor: '#fff',
      messageColor: '#fff',
      iconColor: '#fff',
      backgroundColor: '#ff533d',
      progressBarColor: '#fff',
      position: position,
      transitionIn: 'fadeInDown',
      close: false,
      timeout: t,
      zindex: 99999,
    })
  },
}
