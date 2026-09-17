/*! widgets.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Widgets js file
========================================================================== */

$(function () {
  'use strict'

  if ($('.schedule').length) {
    var style = document.createElement('style')
    document.head.appendChild(style)

    var headerDot = document.querySelector('.day-header-bg')
    var headerDotClasses = ['primary', 'pink', 'purple', 'green']

    var headerCloseBtn = document.querySelector('.day-header-close')

    var dayContainer = document.querySelector('.schedule-day-container')
    var toggleFab = document.querySelector('.next-fab')
    var dayHeaderTitleDay = document.querySelector('.day-header-title-day')
    var dayHeaderContent = document.querySelector('.day-header-content')
    var dayHeaderEvent = document.querySelector('.day-header-event')
    var dayContent = document.querySelector('.day-content')
    var dayContentDetails = document.querySelector('.day-content').children
    var dayHeader = document.querySelector('.day-header')

    dayContent.addEventListener('scroll', function (_) {
      if (_.target.scrollTop > 155) {
        if (dayHeader.classList.contains('day-header--large')) {
          dayHeader.classList.remove('day-header--large')
          dayHeader.classList.add('sticky')
          dayHeader.style.height = 58 + 'px'
        }
      } else if (_.target.scrollTop < 155) {
        if (!dayHeader.classList.contains('day-header--large')) {
          dayHeader.classList.add('day-header--large')
          dayHeader.classList.remove('sticky')
          dayHeader.style.height = 280 + 'px'
        }
        dayHeader.style.height = 200 - _.target.scrollTop + 'px'
      }
    })

    headerCloseBtn.addEventListener('click', function (_) {
      dayContainer.classList.add('animate-out')

      setTimeout(function () {
        dayContainer.classList.add('hidden')
        dayContainer.classList.remove('animate-out')
        dayHeaderContent.classList.remove('animate-in')
        dayContent.classList.remove('animate-in')
        dayHeader.classList.add('day-header--large')
        dayHeader.classList.remove('sticky')
        dayContent.scrollTop = 0
        headerCloseBtn.classList.remove('animate')
        headerDot.classList.remove('animate')
        headerDotClasses.forEach(function (c) {
          headerDot.classList.remove(c)
        })
        toggleFab.classList.remove('is-hidden')
        style.innerHTML = ''
      }, 155)
    })

    Array.from(document.querySelectorAll('[data-day]')).forEach(function (day) {
      var selector =
        '.schedule .schedule-calendar .calendar-row .day.event[data-day="' +
        day.dataset.day +
        '"]:before'
      var colorClass = headerDotClasses.filter(function (c) {
        return day.classList.contains(c)
      })[0]

      day.addEventListener('click', function (_) {
        var animate = _.target.classList.contains('animate')
        var targetDetails = _.target.getAttribute('data-content')
        var contentBlock = '#event-' + _.target.dataset.content
        //var eventContentActive = document.getElementsByClassName('event-details-wrap is-active');
        console.log(dayContentDetails)
        toggleFab.classList.add('is-hidden')
        dayContainer.classList.remove('hidden')
        $('.event-details-wrap').removeClass('is-active')
        $(contentBlock).addClass('is-active')
        //dayContentDetails.classList.remove('is-active');
        //contentContent.classList.add('is-active');
        headerDot.classList.remove('animate')
        headerDotClasses.forEach(function (c) {
          headerDot.classList.remove(c)
        })

        dayHeaderTitleDay.innerText = day.dataset.day
        dayHeaderEvent.innerText = day.dataset.event

        if (!animate) {
          style.innerHTML =
            selector +
            ' {\n            top: ' +
            _.target.offsetTop +
            'px;\n            left: ' +
            _.target.offsetLeft +
            'px;\n          }'
        } else {
          style.innerHTML = ''
        }
        _.target.classList.add('animate')

        // Just above the bottom of the header
        // Math done from the vars in the stylus
        var endPos = { x: 55, y: 166 }

        style.innerHTML =
          selector +
          ' {\n            top: ' +
          _.target.offsetTop +
          'px;\n            left: ' +
          _.target.offsetLeft +
          'px;\n          }\n         ' +
          selector +
          ' {\n            transform: translate(\n              ' +
          (String(endPos.x - _.target.offsetLeft) + 'px') +
          ',\n              ' +
          (String(endPos.y - _.target.offsetTop) + 'px') +
          '\n            )\n        }'

        setTimeout(function () {
          _.target.classList.remove('animate')
          headerDot.classList.add(colorClass)
          headerDot.classList.add('animate')
          dayContent.classList.add('animate-in')

          setTimeout(function () {
            headerCloseBtn.classList.add('animate')
            dayHeaderContent.classList.add('animate-in')
          }, 150)
        }, 150)
      })
    })

    $('.next-fab').on('click', function () {
      $(this).toggleClass('is-toggled')
      $('.schedule-events').slideToggle()
    })
  }

  if ($('.add-transition').length) {
    //Add a recommended page to favorites
    $('.add-transition').on('click', function () {
      var $this = $(this)
      var itemName = $this
        .closest('.transition-block')
        .find('.page-meta span:first-child')
        .text()
      var successIndicator = `
                <div class="checkmark-wrapper">
                    <svg class="checkmark is-xs" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
                        <circle class="checkmark__circle" cx="26" cy="26" r="25" fill="none"/>
                        <path class="checkmark__check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                    </svg>
                </div>
            `

      $(this).addClass('is-hidden')
      $(this).closest('.transition-block').append(successIndicator)

      //Show a success toast
      setTimeout(function () {
        if ($this.closest('.transition-block').hasClass('page-block')) {
          iziToast.show({
            maxWidth: '280px',
            class: 'success-toast',
            icon: 'mdi mdi-bookmark-plus',
            title: '',
            message: '' + itemName + ' has been added to your bookmarks',
            titleColor: '#fff',
            messageColor: '#fff',
            iconColor: '#fff',
            backgroundColor: '#344258',
            progressBarColor: '#0062ff',
            position: 'bottomRight',
            transitionIn: 'fadeInUp',
            close: false,
            timeout: 1800,
            zindex: 99999,
          })
        } else {
          iziToast.show({
            maxWidth: '280px',
            class: 'success-toast',
            icon: 'mdi mdi-email-check',
            title: '',
            message: 'A friend request has been sent to ' + itemName + '',
            titleColor: '#fff',
            messageColor: '#fff',
            iconColor: '#fff',
            backgroundColor: '#344258',
            progressBarColor: '#0062ff',
            position: 'bottomRight',
            transitionIn: 'fadeInUp',
            close: false,
            timeout: 1800,
            zindex: 99999,
          })
        }
      }, 1000)
    })
  }
})
