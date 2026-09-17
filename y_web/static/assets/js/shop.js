'use strict'

function initSpinner(price) {
  $('.spinner .add')
    .off()
    .on('click', function () {
      var $this = $(this)
      var $input = $this.closest('.spinner').find('input')
      var value = parseInt($input.val())
      value = ++value
      $input.val(value).trigger('change')
    })

  $('.spinner .remove')
    .off()
    .on('click', function () {
      var $this = $(this)
      var $input = $this.closest('.spinner').find('input')
      var value = parseInt($input.val())
      value = --value
      if (value < 1) {
        value = 1
      }
      $input.val(value).trigger('change')
    })

  $('.spinner input')
    .off()
    .on('change', function () {
      var $this = $(this)
      var value = parseInt($this.val())
      console.log(value)
      $this.closest('.spinner').find('.value').html(value)

      var newPrice = price * value
      $('#quickview-button-price').html(newPrice.toFixed(2))
    })
}

$(function () {
  if ($('#shop-page').length) {
    //Tabs
    $('.store-tabs .tab-control').on('click', function () {
      var targetSection = $(this).attr('data-tab')
      $(this)
        .closest('.store-tabs')
        .find('.tab-control')
        .removeClass('is-active')
      $(this).addClass('is-active')

      $('.store-tab-pane').removeClass('is-active')
      $('#' + targetSection).addClass('is-active')
    })

    //Product quickview
    $('.quickview-trigger').on('click', function () {
      var $this = $(this)
      var path = $this.closest('.product-card').attr('data-path')
      var productName = $this.closest('.product-card').attr('data-name')
      var productPrice = parseInt(
        $this.closest('.product-card').attr('data-price'),
      )
      var productImage = $this.closest('.product-card').find('img').attr('src')
      var productColors = $this.closest('.product-card').attr('data-colors')
      var productVariants = $this.closest('.product-card').attr('data-colors')

      $('#quickview-name').html(productName)
      $('.product-quickview .product-image img').attr('src', productImage)
      $('#quickview-price, #quickview-button-price').html(
        productPrice.toFixed(2),
      )

      setTimeout(function () {
        $('.quickview-loader').removeClass('is-active')
      }, 1000)

      initSpinner(productPrice)

      if (productColors === 'true') {
        $('#color-properties').removeClass('is-hidden')
        $('#color-properties input')
          .off()
          .on('change', function () {
            var value = $(this).attr('id')
            $('.product-quickview .product-image img').attr(
              'src',
              path + '-' + value + '.svg',
            )
          })
      }

      $('#product-quickview').addClass('is-active')
    })

    $('.quickview-background').on('click', function () {
      $('#product-quickview').removeClass('is-active')
      $('.quickview-loader').addClass('is-active')
      $('#color-properties').addClass('is-hidden')
      $('.spinner input').val('1')
      $('.spinner .value').html('1')
    })
  }

  if ($('.products-navigation').length) {
    $(window).on('scroll', function () {
      var height = $(window).scrollTop()
      if (height > 65) {
        $('.products-navigation').addClass('is-active')
      } else {
        $('.products-navigation').removeClass('is-active')
        $('.navigation-panel').fadeOut()
        $('.products-navigation .shop-action').removeClass('is-active')
      }
    })

    $('.products-navigation .shop-action').on('click', function () {
      var targetPanel = $(this).attr('data-panel')
      if ($(this).hasClass('is-active')) {
        $(this).removeClass('is-active')
      } else {
        $(this).addClass('is-active')
      }
      $('#' + targetPanel).slideToggle()
    })

    initComboBox()
  }

  //Checkout
  if ($('#checkout-button').length) {
    //Checkout next
    $('#checkout-button').on('click', function () {
      var $this = $(this)
      var title = $('#checkout-step-title')
      var backButton = $('#checkout-back')
      var nextStep = parseInt($this.attr('data-step'))
      var prevStep = parseInt($('#checkout-back').attr('data-step'))

      $this.addClass('is-loading')

      setTimeout(function () {
        $this.removeClass('is-loading')
        $('.checkout-section').removeClass('is-active')
        $('#checkout-section-' + nextStep).addClass('is-active')
        $this.attr('data-step', nextStep + 1)
        backButton.attr('data-step', prevStep + 1)

        if (nextStep === 2) {
          title.html('2. Choose a shipping address')
          if ($('.shipping-address input:checked').length === 0) {
            $this.addClass('is-disabled')
          } else {
            $this.removeClass('is-disabled')
          }
        } else if (nextStep === 3) {
          title.html('3. Choose a shipping method')
          if ($('.shipping-box input:checked').length === 0) {
            $this.addClass('is-disabled')
          } else {
            $this.removeClass('is-disabled')
          }
        } else if (nextStep === 4) {
          $('.shipping-logo').addClass('is-active')
          title.html('4. Choose a billing address')
          if ($('.billing-address input:checked').length === 0) {
            $this.addClass('is-disabled')
          } else {
            $this.removeClass('is-disabled')
          }
        } else if (nextStep === 5) {
          var url = window.location.href
          if (url.indexOf('navbar-v1')) {
            window.location.href = '/navbar-v1-ecommerce-payment.html'
          } else if (url.indexOf('navbar-v2')) {
            window.location.href = '/navbar-v2-ecommerce-payment.html'
          } else if (url.indexOf('sidebar-v1')) {
            window.location.href = '/sidebar-v1-ecommerce-payment.html'
          }
        }
      }, 800)
    })

    //Checkout back
    $('#checkout-back').on('click', function () {
      var $this = $(this)
      var title = $('#checkout-step-title')
      var backButton = $('#checkout-back')
      var prevStep = parseInt($('#checkout-back').attr('data-step'))

      $this.addClass('is-loading')

      setTimeout(function () {
        $this.removeClass('is-loading')
        $('.checkout-section').removeClass('is-active')
        $('#checkout-section-' + prevStep).addClass('is-active')
        $('#checkout-button')
          .removeClass('is-disabled')
          .attr('data-step', prevStep + 1)
        $this.attr('data-step', prevStep - 1)

        if (prevStep === 0) {
          window.location.href = '/ecommerce-cart.html'
        } else if (prevStep === 1) {
          title.html('1. Confirm your order')
        } else if (prevStep === 2) {
          title.html('2. Choose a shipping address')
          $('.shipping-logo').removeClass('is-active')
        } else if (prevStep === 3) {
          title.html('3. Choose a shipping method')
          $('.shipping-logo').addClass('is-active')
        }
      }, 800)
    })

    //Steps validation
    $('.address-box input').on('change', function () {
      $('#checkout-button').removeClass('is-disabled')
      var address = $(this)
        .closest('.address-box')
        .find('.address-box-inner')
        .html()
      $('#shipping-address-box p').remove()
      $('#shipping-address-box').append(address)
      $('#shipping-placeholder-box').addClass('is-hidden')
      $('#shipping-address-box').removeClass('is-hidden')
    })

    $('.shipping-box input').on('change', function () {
      var shipppingLogo = $(this)
        .closest('.shipping-box')
        .find('img')
        .attr('src')
      $('.shipping-logo').attr('src', shipppingLogo).addClass('is-active')
      $('#shipping-amount')
        .find('.is-text')
        .removeClass('is-text')
        .html('15.00')
      $('#total-amount span:nth-child(2)').html('216.92')
      $('#checkout-button').removeClass('is-disabled')
    })
  }

  //Payment
  if ($('#payment-container').length) {
    // Create a Stripe client
    var stripe = Stripe('pk_test_6pRNASCoBOKtIshFeQd4XMUh')
    // Create an instance of Elements
    var elements = stripe.elements()

    // Custom styling can be passed to options when creating an Element.
    // (Note that this demo uses a wider set of styles than the guide below.)
    var theme = window.localStorage.getItem('theme')
    var style

    if (theme != null && theme != undefined && theme != 'dark') {
      style = {
        base: {
          // Add your base input styles here. For example:
          fontSize: '14px',
          color: '#595d6e',
        },
      }
    } else {
      style = {
        base: {
          // Add your base input styles here. For example:
          iconColor: '#fff',
          fontSize: '14px',
          color: '#fff',
          '::placeholder': {
            color: '#6f809e',
          },
        },
      }
    }

    // Create an instance of the card Element
    var card = elements.create('card', { style: style })

    // Add an instance of the card Element into the `card-element` <div>
    card.mount('#card-element')

    // Handle real-time validation errors from the card Element.
    card.addEventListener('change', function (event) {
      var displayError = document.getElementById('card-errors')
      if (event.error) {
        displayError.textContent = event.error.message
      } else {
        displayError.textContent = ''
      }
    })

    // Handle form submission
    var form = document.getElementById('stripe-payment-form')
    form.addEventListener('submit', function (event) {
      event.preventDefault()

      stripe.createToken(card).then(function (result) {
        if (result.error) {
          // Inform the user if there was an error
          var errorElement = document.getElementById('card-errors')
          errorElement.textContent = result.error.message
        } else {
          // Send the token to your server
          stripeTokenHandler(result.token)
        }
      })
    })

    //Submit Payment
    $('.is-button .buttons').on('click', function () {
      var $this = $(this)
      $('#payment-button').addClass('is-loading')

      setTimeout(function () {
        $('#payment-button').removeClass('is-loading')
        $(
          '#payment-container, #confirmation-container, .header-actions .button',
        ).toggleClass('is-hidden')
      }, 2000)
    })
  }
})
