/*! compose.js | Friendkit | © Css Ninja. 2019-2021 */

/* ==========================================================================
Functions
========================================================================== */

'use strict'

//The following functions help trigger the autocompletes dropdowns

function openFriendsDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#feed-users-autocpl').focus()
  $('#feed-users-autocpl').attr('value', '')
  $('#feed-users-autocpl').triggerHandler(e)
}

function openActivitiesDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  /*$('#activities-autocpl').focus()
  $('#activities-autocpl').attr('value', '')
  $('#activities-autocpl').triggerHandler(e)*/
}

function openMoodDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#mood-autocpl').focus()
  $('#mood-autocpl').attr('value', '')
  $('#mood-autocpl').triggerHandler(e)
}

function openDrinksDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#drinking-autocpl').focus()
  $('#drinking-autocpl').attr('value', '')
  $('#drinking-autocpl').triggerHandler(e)
}

function openEatsDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#eating-autocpl').focus()
  $('#eating-autocpl').attr('value', '')
  $('#eating-autocpl').triggerHandler(e)
}

function openReadsDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#reading-autocpl').focus()
  $('#reading-autocpl').attr('value', '')
  $('#reading-autocpl').triggerHandler(e)
}

function openWatchDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#watching-autocpl').focus()
  $('#watching-autocpl').attr('value', '')
  $('#watching-autocpl').triggerHandler(e)
}

function openTravelDrop() {
  var e = $.Event('keyup', { keyCode: 65, which: 65 })
  $('#travel-autocpl').focus()
  $('#travel-autocpl').attr('value', '')
  $('#travel-autocpl').triggerHandler(e)
}

function readURL(input) {
  if (input.files && input.files[0]) {
    var reader = new FileReader()
    reader.onload = function (e) {
      var deleteIcon = feather.icons.x.toSvg()
      var template = `
                <div class="upload-wrap">
                    <img src="${e.target.result}" alt="">
                    <span class="remove-file">
                        ${deleteIcon}
                    </span>
                </div>
            `

      $('#feed-upload').append(template)
      $('#feed-upload-input-1, #feed-upload-input-2').attr('disabled', true)

      $('.remove-file').on('click', function () {
        $('#feed-upload-input-1, #feed-upload-input-2')
          .val('')
          .attr('disabled', false)
        $(this).closest('.upload-wrap').remove()
      })
    }
    reader.readAsDataURL(input.files[0])
  }
}

function albumsHelp() {
  $('#albums-help-modal .next-modal').one('click', function () {
    $(this)
      .closest('.card-body')
      .find('.content-block, .dot')
      .toggleClass('is-active')
    $(this).text('got it').off()
    endAlbumHelp()
  })
}

function endAlbumHelp() {
  $('#albums-help-modal .next-modal').on('click', function () {
    var $this = $(this)
    var albumsModal = $this.attr('data-modal')
    $this.closest('.modal').removeClass('is-active')
    $('#' + albumsModal).addClass('is-active')
    setTimeout(function () {
      $this
        .closest('.card-body')
        .find('.content-block, .dot')
        .toggleClass('is-active')
      $this.text('Next').off()
      albumsHelp()
    }, 800)
  })
}

function videosHelp() {
  $('#videos-help-modal .next-modal').one('click', function () {
    $(this)
      .closest('.card-body')
      .find('.content-block, .dot')
      .toggleClass('is-active')
    $(this).text('got it').off()
    endVideoHelp()
  })
}

function endVideoHelp() {
  $('#videos-help-modal .next-modal').on('click', function () {
    var $this = $(this)
    var videosModal = $(this).attr('data-modal')
    $this.closest('.modal').removeClass('is-active')
    if (window.matchMedia('(orientation: portrait)').matches) {
      $('#no-stream-modal').addClass('is-active')
    } else {
      $('#' + videosModal).addClass('is-active')
    }
    setTimeout(function () {
      $this
        .closest('.card-body')
        .find('.content-block, .dot')
        .toggleClass('is-active')
      $this.text('Next').off()
      videosHelp()
    }, 800)
  })
}

/* ==========================================================================
Compose card events
========================================================================== */

if ($('#compose-card').length) {
  //Open publish mode
  $('#publish').on('click', function () {
    $('.app-overlay').addClass('is-active')
    $('.is-new-content').addClass('is-highlighted')
  })

  //Open publish mode from new story-button
  $('#add-story-button').on('click', function () {
    $('.app-overlay').addClass('is-active')
    $('.is-new-content').addClass('is-highlighted')
    $('.target-channels .channel').each(function () {
      if ($(this).find('input[type="checkbox"]').prop('checked')) {
        $(this).find('input[type="checkbox"]').prop('checked', false)
      } else {
        $(this).find('input[type="checkbox"]').prop('checked', true)
      }
    })
  })

  //Close compose box
  $('.close-publish').on('click', function () {
    $('.app-overlay').removeClass('is-active')
    $('.is-new-content').removeClass('is-highlighted')
    $('#compose-search, #extended-options, .is-suboption').addClass('is-hidden')
    $('#basic-options, #open-compose-search').removeClass('is-hidden')
  })

  //Expand compose box
  $('#show-compose-friends').on('click', function () {
    $(this).addClass('is-hidden')
    $('.friends-list').removeClass('is-hidden')
    $('.hidden-options').addClass('is-opened')
  })

  //Open extended options
  $('#open-extended-options').off('click').on('click', function () {
    // Toggle compose options without overlay or highlight
    $('.compose-options').toggleClass('is-hidden')
  })

  //Open compose box search
  $('#open-compose-search').on('click', function () {
    $('#compose-search, #open-compose-search').toggleClass('is-hidden')
  })

  //Enable checkbox checking and unchecking by clicking on the row
  $('.channel, .friend-block').on('click', function (e) {
    if (e.target !== this) {
      return false
    } else {
      if ($(this).find('input[type="checkbox"]').prop('checked')) {
        $(this).find('input[type="checkbox"]').prop('checked', false)
      } else {
        $(this).find('input[type="checkbox"]').prop('checked', true)
      }
    }
  })

  //Suboptions
  $('#open-tag-suboption').on('click', function () {
    $('.is-suboption').addClass('is-hidden')
    $('#tag-suboption').removeClass('is-hidden')
    //Open autocomplete dropdown
    openFriendsDrop()
  })

  //Show activities
  $('#show-activities, #extended-show-activities').on('click', function () {
    $('.app-overlay').addClass('is-active')
    $('.is-new-content').addClass('is-highlighted')
    //$('.compose-options').toggleClass('is-hidden');
    $('.is-suboption').addClass('is-hidden')
    $('#activities-suboption').removeClass('is-hidden')
    //Open autocomplete dropdown
    openActivitiesDrop()
  })

  //
  $('.input-block, .close-icon.is-subactivity').on('click', function () {
    $('#activities-autocpl-wrapper').toggleClass('is-hidden')
    $('.is-activity').addClass('is-hidden')
    $('.easy-autocomplete-container li').removeClass('selected')
    $('.mood-display').html('')
    //Open autocomplete dropdown
    openActivitiesDrop()
  })

  //Show location input
  $('#open-location-suboption').on('click', function () {
    $('.is-suboption').addClass('is-hidden')
    $('#location-suboption').removeClass('is-hidden')
  })

  //Show URL input
  $('#open-link-suboption').on('click', function () {
    $('.is-suboption').addClass('is-hidden')
    $('#link-suboption').removeClass('is-hidden')
  })

  //Show GIF input
  $('#open-gif-suboption').on('click', function () {
    $('.is-suboption').addClass('is-hidden')
    $('#gif-suboption').removeClass('is-hidden')
  })

  //Close autocomplete sections when clicking on the X
  $('.is-autocomplete .close-icon.is-main').on('click', function () {
    $(this).closest('.is-suboption').addClass('is-hidden')
  })

  //Init comments
  initPostComments()

  //Handle adding member in a new group (modal)
  $('#new-group-list .friend-block').on('click', function () {
    var selectedRef = $(this).closest('.friend-block').attr('data-ref')
    var selectedAvatar = $(this)
      .closest('.friend-block')
      .find('img')
      .attr('src')
    var selectedFriend = $(this)
      .closest('.friend-block')
      .find('.friend-name')
      .text()
    var checkIcon = feather.icons.check.toSvg()

    var html = ''

    if ($(this).find('input').prop('checked')) {
      if ($('#' + selectedRef).length) {
        return false
      } else {
        html = `
                    <div id="${selectedRef}" class="selected-friend-block">
                        <div class="image-wrapper">
                            <img class="friend-avatar" src="${selectedAvatar}" alt="">
                            <div class="checked-badge">
                                ${checkIcon}
                            </div>
                        </div>
                        <div class="friend-name">${selectedFriend}</div>
                    </div>
                `
        $('#selected-list').append(html)

        var selectedCount = $('#selected-list .selected-friend-block').length
        $('#selected-friends-count').html(selectedCount)
      }
    } else {
      console.log('it has been unchecked!')
      $('#' + selectedRef).remove()

      var selectedCount = $('#selected-list .selected-friend-block').length
      $('#selected-friends-count').html(selectedCount)
    }
  })

  //Help modal before albums management
  albumsHelp()

  //Toggle tag friends input in album modal
  $('#tagged-in-album button').on('click', function () {
    $(this).addClass('is-hidden')
    $(this)
      .closest('.tagged-in-album')
      .find('.field, p')
      .toggleClass('is-hidden')
  })

  //Toggle datepicker input in album modal
  $('#album-date button').on('click', function () {
    $(this).addClass('is-hidden')
    $(this).closest('.album-date').find('p').addClass('is-hidden')
    $(this).closest('.album-date').find('.control').removeClass('is-hidden')
  })

  //Init datepicker inside album modal
  $('#album-datepicker').datepicker({
    format: 'mm-dd-yyyy',
    container: 'body',
    autoHide: true,
    offset: 0,
  })

  //Help modal before live video
  videosHelp()

  // Override create post trigger to display inline compose without modal overlay
  $('#create-post-trigger').off('click').on('click', function(e) {
    e.preventDefault();
    // Hide any overlay
    $('.app-overlay').removeClass('is-active');
    // Highlight inline compose-card
    $('#create-post-trigger').hide();
    $('#compose-card').show();
  });
}
