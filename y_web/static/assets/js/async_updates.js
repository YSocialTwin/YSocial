$(document).on('click','#publish-button',function(e) {
    $(document).ajaxStop(function (){
        window.location.reload();
    });
      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/publish',
        data:{
          post: document.getElementById("publish").value,
            url: document.getElementById("link_post").value,
            annotation: document.getElementById("activities").value,
        },
      })
    });

$(document).on('click', '.dropdown-item#delete_post', function(e) {
      e.preventDefault();

      var action = e.currentTarget;
      var post_id = action.getAttribute('val');
      if (!post_id) {
          return;
      }

      var elem = document.getElementById("post-" + post_id) || document.getElementById("feed-post-" + post_id);
      if (elem && elem.parentElement) {
          elem.parentElement.style.visibility = 'hidden';
          elem.parentElement.style.display = 'none';
      } else if (elem) {
          elem.style.visibility = 'hidden';
          elem.style.display = 'none';
      }

      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/delete_post',
        data:{
          post_id: post_id,
        },
        error: function () {
            if (elem && elem.parentElement) {
                elem.parentElement.style.visibility = '';
                elem.parentElement.style.display = '';
            } else if (elem) {
                elem.style.visibility = '';
                elem.style.display = '';
            }
        }
      })
    });

$(document).on('click','.child_sub',function(e) {
      var toggle = e.currentTarget;
      var post_id = toggle.getAttribute('val');
      var elem = document.getElementById("child-"+post_id);
      if (!elem) {
          return;
      }
      if (toggle.textContent.trim() === "Less") {
          toggle.textContent = "More"
          elem.style.visibility = 'hidden';
          elem.style.display = 'none'
      }
      else {
          toggle.textContent = "Less"
          elem.style.visibility = 'visible';
          elem.style.display = 'block'
      }
      e.preventDefault();
    });

$(document).on('click','#add_comment, .add-comment-button',function(e) {
    e.preventDefault();

    var button = e.currentTarget;
    if (!button || button.dataset.pending === '1') {
        return;
    }

    var elem_id = button.getAttribute('val');
    var content = document.getElementById(`comment-${elem_id}`);
    if (!elem_id || !content) {
        return;
    }

    button.dataset.pending = '1';
    button.disabled = true;

    $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/publish_comment',
        data: {
            post: content.value,
            parent: elem_id,
        },
        success: function () {
            window.location.reload();
        },
        complete: function () {
            delete button.dataset.pending;
            button.disabled = false;
        }
    });
});

$(document).on('click','.share-button',function(e) {

        var col = rgbToHex(e.target.style.background);

      if (rgbToHex(e.target.style.background) !== "#6aa3e7"){
          var elem_id = e.target.getAttribute('id').slice(1);
          e.target.style.background = '#6aa3e7';
          e.target.style.color = '#ffffff';

          var p = document.getElementById(`share-count-${elem_id}`);
          p.firstElementChild.firstElementChild.style.stroke = "#ffffff";
          p.firstElementChild.firstElementChild.firstElementChild.style.stroke = "#ffffff";
          p.firstElementChild.firstElementChild.lastElementChild.style.color = "#ffffff";
          var count = p.firstElementChild.firstElementChild.lastElementChild;
          let currentValue = parseInt(count.textContent, 10);

          currentValue++;
          count.textContent = currentValue;

        }
      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/share_content',
        data: {
            post_id: elem_id,
        },
      })
    });

$(document).on('click','.like-button',function(e)
                   {
      e.preventDefault();
      var button = e.currentTarget || e.target.closest('.like-button');
      if (!button || !button.getAttribute('id')) {
          return;
      }

      var col = rgbToHex(button.style.background);

      if (rgbToHex(button.style.background) !== "#6aa3e7"){
          var elem_id = button.getAttribute('id').slice(1);
          button.style.background = '#6aa3e7';
          button.style.color = '#ffffff';

          var p = document.getElementById(`likes-count-${elem_id}`);
          p.firstElementChild.firstElementChild.firstElementChild.style.stroke = "#ffffff";
          p.firstElementChild.firstElementChild.lastElementChild.style.color = "#ffffff";
          var count = p.firstElementChild.firstElementChild.lastElementChild;

          let currentValue = parseInt(count.textContent, 10);

          currentValue++;
          count.textContent = currentValue;

          var opp = document.getElementById(`dislikes-count-${elem_id}`);
          var color = opp.firstElementChild.firstElementChild.lastElementChild.style.color

          if (color === undefined || rgbToHex(color) === "#ffffff"){
              document.getElementById(`d${elem_id}`).style.background = "#ffffff";
              opp.firstElementChild.firstElementChild.firstElementChild.style.stroke = "#888da8";
              opp.firstElementChild.firstElementChild.lastElementChild.style.color = "#888da8";
              var count_opp = opp.firstElementChild.firstElementChild.lastElementChild;
              let opp_currentValue = parseInt(count_opp.textContent, 10);
              opp_currentValue--;
              count_opp.textContent = opp_currentValue;
          }
        }
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/react_to_content',
        data: {
            post_id: elem_id,
            action: "like",
        },
      })
    });


$(document).on('click','.dislike-button',function(e)
                   {
      e.preventDefault();
      var button = e.currentTarget || e.target.closest('.dislike-button');
      if (!button || !button.getAttribute('id')) {
          return;
      }

      if (rgbToHex(button.style.background) !== "#6aa3e7"){
          var elem_id = button.getAttribute('id').slice(1);

          button.style.background = '#6aa3e7';
          button.style.color = '#ffffff';

          var p = document.getElementById(`dislikes-count-${elem_id}`);
          p.firstElementChild.firstElementChild.firstElementChild.style.stroke = "#ffffff";
          p.firstElementChild.firstElementChild.lastElementChild.style.color = "#ffffff";
          var count = p.firstElementChild.firstElementChild.lastElementChild;
          let currentValue = parseInt(count.textContent, 10);

          currentValue++;
          count.textContent = currentValue;

          var opp = document.getElementById(`likes-count-${elem_id}`);
          var color = opp.firstElementChild.firstElementChild.lastElementChild.style.color

          if (color === undefined || rgbToHex(color) === "#ffffff"){
              document.getElementById(`l${elem_id}`).style.background = "#ffffff";
              opp.firstElementChild.firstElementChild.firstElementChild.style.stroke = "#888da8";
              opp.firstElementChild.firstElementChild.lastElementChild.style.color = "#888da8";
              var count_opp = opp.firstElementChild.firstElementChild.lastElementChild;
              let opp_currentValue = parseInt(count_opp.textContent, 10);
              opp_currentValue--;
              count_opp.textContent = opp_currentValue;
          }
        }
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/react_to_content',
        data: {
            post_id: elem_id,
            action: "dislike",
        },
      })
    });

$(document).on('click', '.report-fab, .report-count', function (e) {
    e.preventDefault();

    var button = e.currentTarget;
    if (button.dataset.pending === '1' || button.dataset.reported === '1') {
        return;
    }

    button.dataset.pending = '1';

    $.ajax({
        type: 'GET',
        url: button.getAttribute('href'),
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        },
        success: function (response) {
            var nextCount = parseInt(response && response.report_count, 10);
            if (!Number.isNaN(nextCount)) {
                var countEl = button.querySelector('span');
                if (countEl) {
                    countEl.textContent = nextCount;
                }
            }
            button.dataset.reported = '1';
            button.classList.add('is-active');
        },
        complete: function () {
            delete button.dataset.pending;
        }
    });
});


function editLink(id){
    var commentForm = document.getElementById(`comment_form-${id}`);
    var messageEl = document.getElementById(`message-${id}`);

    if (!commentForm) {
        return false;
    }

    var test = commentForm.style.display;
    if (!test || test === "none"){
        commentForm.style.display = "block";
        if (messageEl) {
            messageEl.style.display = "none";
        }
    }
    else {
        commentForm.style.display = "none";
        if (messageEl) {
            messageEl.style.display = "block";
        }
    }
    return false;
}

$(document).on('click', '.meta-chip-toggle', function (e) {
    e.preventDefault();

    var button = e.currentTarget;
    var targetId = button.getAttribute('data-target');
    var target = targetId ? document.getElementById(targetId) : null;
    if (!target) {
        return;
    }

    var isHidden = target.classList.contains('is-hidden');
    target.classList.toggle('is-hidden', !isHidden);
    button.textContent = isHidden
        ? (button.getAttribute('data-label-less') || 'Less')
        : (button.getAttribute('data-label-more') || 'More');
    button.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
});


$(document).on('click','.like-count',function(e) {
    let idc = e.target.id;
    if (e.target.id){
        idc = e.target.id;
    }
    else{
        idc = e.target.parentElement.id;
    }
    let base = document.getElementById(idc);

    let elem_id = idc.split('-')[2];

    if (rgbToHex(base.lastElementChild.style.color) !== "#69a2e6") {

        base.firstElementChild.style.stroke = "#69a2e6";
        base.lastElementChild.style.color = "#69a2e6"

        let currentValue = parseInt(base.lastElementChild.textContent, 10);
        currentValue++;
        base.lastElementChild.textContent = currentValue;

        var opp = document.getElementById(`dislike-count-${elem_id}`);
        var color = opp.firstElementChild.style.stroke;

        if (color === undefined || rgbToHex(color) === "#69a2e6"){
            opp.firstElementChild.style.stroke = "#888da8";
            opp.lastElementChild.style.color = "#888da8";

            let currentValue = parseInt(opp.lastElementChild.textContent, 10);
            currentValue--;
            opp.lastElementChild.textContent = currentValue;
        }
    }

    e.preventDefault();
      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/react_to_content',
        data: {
            post_id: elem_id,
            action: "like",
        },
      })
    });

$(document).on('click','.dislike-count',function(e) {

    let idc = e.target.id;
    if (e.target.id){
        idc = e.target.id;
    }
    else{
        idc = e.target.parentElement.id;
    }
    let base = document.getElementById(idc);
    let elem_id = idc.split('-')[2];

    if (rgbToHex(base.lastElementChild.style.color) !== "#69a2e6") {

        base.firstElementChild.style.stroke = "#69a2e6";
        base.lastElementChild.style.color = "#69a2e6"

        let currentValue = parseInt(base.lastElementChild.textContent, 10);
        currentValue++;
        base.lastElementChild.textContent = currentValue;

        var opp = document.getElementById(`like-count-${elem_id}`);
        var color = opp.firstElementChild.style.stroke;

        if (color === undefined || rgbToHex(color) === "#69a2e6"){
            opp.firstElementChild.style.stroke = "#888da8";
            opp.lastElementChild.style.color = "#888da8";

            let currentValue = parseInt(opp.lastElementChild.textContent, 10);
            currentValue--;
            opp.lastElementChild.textContent = currentValue;
        }
    }

    e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/react_to_content',
        data: {
            post_id: elem_id,
            action: "dislike",
        },
      })
    });


$(document).on('click','.share-count',function(e) {

    let idc = e.target.id;
    if (e.target.id){
        idc = e.target.id;
    }
    else{
        idc = e.target.parentElement.id;
    }
    let base = document.getElementById(idc);
    let elem_id = idc.split('-')[2];

    if (rgbToHex(base.lastElementChild.style.color) !== "#69a2e6") {

        base.firstElementChild.style.stroke = "#69a2e6";
        base.lastElementChild.style.color = "#69a2e6"

        let currentValue = parseInt(base.lastElementChild.textContent, 10);
        currentValue++;
        base.lastElementChild.textContent = currentValue;

    }

    e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/share_content',
        data: {
            post_id: elem_id,
        },
      })
    });


function rgbToHex(rgb) {
     if (rgb === ""){ return null}
    const rgbValues = rgb.match(/\d+/g); // Extract numeric values

    return `#${rgbValues
        .map(value => parseInt(value, 10).toString(16).padStart(2, '0'))
        .join('')}`.toLowerCase();
}

$(document).on('click','.cancel-notification',function(e) {
      var post_id = e.target.getAttribute('val');
      document.getElementById(`left-${post_id}`).style.display = 'none';
      document.getElementById(`right-${post_id}`).style.display = 'none';

      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/cancel_notification',
        data:{
          post_id: post_id,
        },
      })
    });
