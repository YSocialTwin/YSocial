/*! lightbox.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Fancybox functions
========================================================================== */

$(function () {
  'use strict'

  //Change demo images
  function changeLightboxImages() {
    $('.fancybox-container [data-demo-src]').each(function () {
      var newSrc = $(this).attr('data-demo-src')
      $(this).attr('src', newSrc)
    })
  }

  if ($('[data-fancybox]').length) {
    var moreIcon = feather.icons['more-vertical'].toSvg()
    var thumbsUpIcon = feather.icons['thumbs-up'].toSvg()
    var lockIcon = feather.icons.lock.toSvg()
    var userIcon = feather.icons.user.toSvg()
    var usersIcon = feather.icons.users.toSvg()
    var globeIcon = feather.icons.globe.toSvg()
    var heartIcon = feather.icons.heart.toSvg()
    var smileIcon = feather.icons.smile.toSvg()
    var messageIcon = feather.icons['message-circle'].toSvg()

    var lightboxContent = ''

    var lightboxComments1 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/dan.jpg" alt="">
                <div class="user-meta">
                    <span>Dan Walker</span>
                    <span><small>2 hours ago</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>12</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>8</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>8</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/dan.jpg" alt="" data-user-popover="1">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Dan Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>28m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>2</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/david.jpg" alt="" data-user-popover="4">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">David Kim</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>15m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/rolf.jpg" alt="" data-user-popover="17">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Rolf Krupp</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>9h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="" data-user-popover="6">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Elise Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>8h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>4</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/rolf.jpg" alt="" data-user-popover="17">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Rolf Krupp</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>7h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>2</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="" data-user-popover="6">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Elise Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>6h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>4</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/lana.jpeg" alt="" data-user-popover="14">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Lana Henrikssen</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>10h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>7</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls has-lightbox-emojis">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    var lightboxComments2 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="">
                <div class="user-meta">
                    <span>Elise Walker</span>
                    <span><small>2 days ago</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>3</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>5</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>5</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/gaelle.jpeg" alt="" data-user-popover="11">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Gaelle Morris</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>2d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="" data-user-popover="6">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Elise Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>4h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/rolf.jpg" alt="" data-user-popover="13">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Rolf Krupp</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>4h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="" data-user-popover="6">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Elise Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>4h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/nelly.png" alt="" data-user-popover="7">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Nelly Schwartz</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>4h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls has-lightbox-emojis">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea comment-textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    var lightboxComments3 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="">
                <div class="user-meta">
                    <span>Stella Bergmann</span>
                    <span><small>Yesterday</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>33</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>9</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>9</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="" data-user-popover="0">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Jenna Davis</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>30m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/lana.jpeg" alt="" data-user-popover="10">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Lana Henrikssen</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>15m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/david.jpg" alt="" data-user-popover="4">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">David Kim</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>12m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/mike.jpg" alt="" data-user-popover="16">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Mike Lasalle</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>8m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="" data-user-popover="2">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing. Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/daniel.jpg" alt="" data-user-popover="3">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Daniel Wellington</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>5h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>3</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/bobby.jpg" alt="" data-user-popover="8">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Bobby Brown</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>7h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>3</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="" data-user-popover="2">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing. Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>7h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment is-nested">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/lana.jpeg" alt="" data-user-popover="10">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Lana Henrikssen</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>15m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls has-lightbox-emojis">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea comment-textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    var profileLightbox1 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                <div class="user-meta">
                    <span>Jenna Davis</span>
                    <span><small>3 days ago</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>32</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>5</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>5</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/bobby.jpg" alt="" data-user-popover="8">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Bobby Brown</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>12</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/daniel.jpg" alt="" data-user-popover="3">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Daniel Wellington</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>15m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>2</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/mike.jpg" alt="" data-user-popover="12">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Mike Lasalle</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>3</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/lana.jpeg" alt="" data-user-popover="10">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Lana Henrikssen</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>3</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/nelly.png" alt="" data-user-popover="9">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Nelly Schwartz</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>2d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea comment-textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    var profileLightbox2 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="">
                <div class="user-meta">
                    <span>Elise Walker</span>
                    <span><small>3 months ago</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>3</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>3</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>3</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="" data-user-popover="2">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>12h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>2</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/nelly.png" alt="" data-user-popover="9">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Nelly Schwartz</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>4h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/bobby.jpg" alt="" data-user-popover="8">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Bobby Brown</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros. Consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>4h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>3</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls has-lightbox-emojis">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea comment-textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    var profileLightbox3 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                <div class="user-meta">
                    <span>Jenna Davis</span>
                    <span><small>oct 17 2018</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>58</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>9</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>927</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/milly.jpg" alt="" data-user-popover="7">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Milly Augustine</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/edward.jpeg" alt="" data-user-popover="5">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Edward Mayers</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore et dolore magna aliqua.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>30m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="" data-user-popover="6">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Elise Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore et dolore magna aliqua.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>15m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="" data-user-popover="2">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1h</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="" data-user-popover="0">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>30m</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/edward.jpeg" alt="" data-user-popover="5">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Edward Mayers</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore et dolore magna aliqua.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>1d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/nelly.png" alt="" data-user-popover="9">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Nelly Schwartz</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>2d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="" data-user-popover="0">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>2d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/elise.jpg" alt="" data-user-popover="6">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Elise Walker</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore et dolore magna aliqua.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>2d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls has-lightbox-emojis">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea comment-textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    var profileLightbox4 = `
            <div class="header">
                <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                <div class="user-meta">
                    <span>Jenna Davis</span>
                    <span><small>oct 17 2018</small></span>
                </div>
                <button type="button" class="button">Follow</button>
                <div class="dropdown is-spaced is-right dropdown-trigger">
                    <div>
                        <div class="button">
                            ${moreIcon}
                        </div>
                    </div>
                    <div class="dropdown-menu" role="menu">
                        <div class="dropdown-content">
                            <div class="dropdown-item is-title has-text-left">
                                Who can see this ?
                            </div>
                            <a href="#" class="dropdown-item">
                                <div class="media">
                                    ${globeIcon}
                                    <div class="media-content">
                                        <h3>Public</h3>
                                        <small>Anyone can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${usersIcon}
                                    <div class="media-content">
                                        <h3>Friends</h3>
                                        <small>only friends can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                            <a class="dropdown-item">
                                <div class="media">
                                    ${userIcon}
                                    <div class="media-content">
                                        <h3>Specific friends</h3>
                                        <small>Don't show it to some friends.</small>
                                    </div>
                                </div>
                            </a>
                            <hr class="dropdown-divider">
                            <a class="dropdown-item">
                                <div class="media">
                                    ${lockIcon}
                                    <div class="media-content">
                                        <h3>Only me</h3>
                                        <small>Only me can see this publication.</small>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="inner-content">
                <div class="live-stats">
                    <div class="social-count">
                        <div class="likes-count">
                            ${heartIcon}
                            <span>33</span>
                        </div>
                        <div class="comments-count">
                            ${messageIcon}
                            <span>8</span>
                        </div>
                    </div>
                    <div class="social-count ml-auto">
                        <div class="views-count">
                            <span>8</span>
                            <span class="views"><small>comments</small></span>
                        </div>
                    </div>
                </div>
                <div class="actions">
                    <div class="action">
                        ${thumbsUpIcon}
                        <span>Like</span>
                    </div>
                    <div class="action">
                        ${messageIcon}
                        <span>Comment</span>
                    </div>
                </div>
            </div>

            <div class="comments-list has-slimscroll">
                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/stella.jpg" alt="" data-user-popover="2">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin ornare magna eros.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>17d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="" data-user-popover="0">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Jenna Davis</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>17d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>4</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/david.jpg" alt="" data-user-popover="4">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">David Kim</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>17d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/milly.jpg" alt="" data-user-popover="7">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Milly Augustine</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>17d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>5</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/daniel.jpg" alt="" data-user-popover="3">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Daniel Wellington</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>17d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>1</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/david.jpg" alt="" data-user-popover="4">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">David Kim</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>18d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="" data-user-popover="0">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Stella Bergmann</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>18d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>8</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="media is-comment">
                    <figure class="media-left">
                        <p class="image is-32x32">
                            <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/mike.jpg" alt="" data-user-popover="12">
                        </p>
                    </figure>
                    <div class="media-content">
                        <div class="username">Mike Lasalle</div>
                        <p>Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempo incididunt ut labore et dolore magna aliqua.</p>
                        <div class="comment-actions">
                            <a href="javascript:void(0);" class="is-inverted">Like</a>
                            <span>18d</span>
                            <div class="likes-count">
                                ${heartIcon}
                                <span>0</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <div class="comment-controls has-lightbox-emojis">
                <div class="controls-inner">
                    <img src="https://via.placeholder.com/300x300" data-demo-src="assets/img/avatars/jenna.png" alt="">
                    <div class="control">
                        <textarea class="textarea comment-textarea is-rounded" rows="1"></textarea>
                        <button class="emoji-button">
                            ${smileIcon}
                        </button>
                    </div>
                </div>
            </div>
        `

    $('[data-fancybox]').each(function () {
      if ($(this).attr('data-lightbox-type') == 'comments') {
        var lightboxContent = $(this).attr('data-fancybox')
        console.log(lightboxContent)
        $(this).fancybox({
          baseClass: 'fancybox-custom-layout',
          keyboard: false,
          infobar: false,
          touch: {
            vertical: false,
          },
          buttons: ['close', 'thumbs', 'share'],
          animationEffect: 'fade',
          transitionEffect: 'fade',
          preventCaptionOverlap: false,
          idleTime: false,
          gutter: 0,
          // Customize caption area
          caption: function (instance) {
            if (lightboxContent == 'post1') {
              return lightboxComments1
            } else if (lightboxContent == 'post2') {
              return lightboxComments2
            } else if (lightboxContent == 'post3') {
              return lightboxComments3
            } else if (lightboxContent == 'profile-post1') {
              return profileLightbox1
            } else if (lightboxContent == 'profile-post2') {
              return profileLightbox2
            } else if (lightboxContent == 'profile-post3') {
              return profileLightbox3
            } else if (lightboxContent == 'profile-post4') {
              return profileLightbox4
            }
          },
          afterShow: function (instance, current) {
            initDropdowns()

            initLightboxEmojis()

            if (env === 'development') {
              changeLightboxImages()
            }
          },
        })
      }
    })
  }
})
