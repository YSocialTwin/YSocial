$(document).on('click','#follow',function(e)
                   {
      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/follow/'+  document.getElementById("follow").getAttribute("res"),
        //data:{
        //  todo:$("#follow").val()
        //},
        //success:function()
        //{
        //  window.location.reload();
        //}
      })
    });




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

$(document).on('click','.dropdown-item',function(e) {
      var post_id = e.target.getAttribute('val');
      var elem = document.getElementById("post-"+post_id);
      elem.parentElement.style.visibility='hidden';
      elem.parentElement.style.display = 'none'
      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/delete_post',
        data:{
          post_id: post_id,
        },
      })
    });

$(document).on('click','.child_sub',function(e) {
      var post_id = e.target.getAttribute('val');
      var elem = document.getElementById("child-"+post_id);
      if (e.target.textContent === "Less") {
          e.target.textContent = "More"
          elem.style.visibility = 'hidden';
          elem.style.display = 'none'
      }
      else {
          e.target.textContent = "Less"
          elem.style.visibility = 'visible';
          elem.style.display = 'block'
      }
      e.preventDefault();
    });

$(document).on('click','#add_comment',function(e) {
    $(document).ajaxStop(function (){
        window.location.reload();
    });
    var elem_id = e.target.getAttribute('val');
      var content = document.getElementById(`comment-${elem_id}`);

      e.preventDefault();
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/publish_comment',
        data: {
            post: content.value,
            parent: elem_id,
        },
      })
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

      var col = rgbToHex(e.target.style.background);

      if (rgbToHex(e.target.style.background) !== "#6aa3e7"){
          var elem_id = e.target.getAttribute('id').slice(1);
          e.target.style.background = '#6aa3e7';
          e.target.style.color = '#ffffff';

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


$(document).on('click','.dislike-button',function(e)
                   {

      if (rgbToHex(e.target.style.background) !== "#6aa3e7"){
          var elem_id = e.target.getAttribute('id').slice(1);

          e.target.style.background = '#6aa3e7';
          e.target.style.color = '#ffffff';

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


function editLink(id){
    var here = document.getElementById(id)
    var test = document.getElementById(`comment_form-${id}`).style.display
    if (!test || test==="none"){
        document.getElementById(`comment_form-${id}`).style.display = "block"; //getElementById
        document.getElementById(`message-${id}`).style.display = "none"
        var message = document.getElementById(`message-${id}`).innerHTML;
        document.getElementById(`add_comment-${id}`).value = message;
    }
    else {
        document.getElementById(`comment_form-${id}`).style.display = "none"; //getElementById
        document.getElementById(`message-${id}`).style.display = "block"
    }
}


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

