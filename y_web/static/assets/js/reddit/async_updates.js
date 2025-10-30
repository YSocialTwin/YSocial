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




// Create Post Button - Expand form
$(document).on('click','#create-post-trigger',function(e) {
    e.preventDefault();
    $('#create-post-trigger').hide();
    $('#compose-card').show();
    $('#post-title').focus();
});

// Auto-resize textarea
$(document).on('input', '#publish', function(e) {
    this.style.height = 'auto';
    this.style.height = Math.max(120, this.scrollHeight) + 'px';
});

// Close button - Collapse form
$(document).on('click','.close-publish',function(e) {
    e.preventDefault();
    $('#compose-card').hide();
    $('#create-post-trigger').show();
    // Clear form fields
    $('#post-title').val('');
    $('#publish').val('');
    $('#link-url').val('');
    $('#image-url').val('');
});

$(document).on('click','#publish-button',function(e) {
    $(document).ajaxStop(function (){
        window.location.reload();
    });
      e.preventDefault();
      
      // Get values from new form fields
      var title = document.getElementById("post-title").value;
      var body = document.getElementById("publish").value;
      var linkUrl = document.getElementById("link-url").value;
      var imageUrl = document.getElementById("image-url").value;
      
      // Combine title and body for post content (Reddit-style)
      var postContent = title;
      if (body.trim()) {
          postContent += "\n\n" + body;
      }
      
      // Use link URL if provided, otherwise use image URL
      var urlToShare = linkUrl || imageUrl || document.getElementById("link_post")?.value || "";
      
      $.ajax({
        type:'GET',
        url:(window.EXP_PREFIX || '') + '/publish_reddit',
        data:{
          post: postContent,
          url: urlToShare,
          annotation: document.getElementById("activities")?.value || "",
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

// Function to refresh vote states from server
function refreshVoteStates() {
    $('.like-button, .dislike-button').each(function() {
        var button = $(this);
        var postId = button.attr('id').slice(1); // Remove l/d prefix
        
        $.ajax({
            type: 'GET',
            url: '/get_vote_state',
            data: { post_id: postId },
            success: function(response) {
                var likeButton = $('#l' + postId);
                var dislikeButton = $('#d' + postId);
                var scoreElement = likeButton.parent().find('span');
                
                // Update colors based on current state
                if (response.is_liked) {
                    likeButton.css('color', '#ff4500');
                } else {
                    likeButton.css('color', '#878a8c');
                }
                
                if (response.is_disliked) {
                    dislikeButton.css('color', '#7193ff');
                } else {
                    dislikeButton.css('color', '#878a8c');
                }
                
                // Update score
                scoreElement.text(response.score);
            }
        });
    });
}

// Refresh vote states when page loads
$(document).ready(function() {
    setTimeout(refreshVoteStates, 500); // Small delay to ensure page is fully loaded
});

// Direct voting functions that can be called from onclick
function handleLikeClick(postId, buttonElement) {
    console.log('Direct like function called for post:', postId);
    
    var button = buttonElement;
    var isCurrentlyLiked = button.style.color.includes('255') && button.style.color.includes('69');
    console.log('Is currently liked:', isCurrentlyLiked);
    
    var scoreElement = button.parentElement.querySelector('span');
    var dislikeButton = document.getElementById('d' + postId);
    var isCurrentlyDisliked = dislikeButton && (dislikeButton.style.color.includes('113') || dislikeButton.style.color.includes('7193ff'));
    
    var currentScore = parseInt(scoreElement.textContent, 10);
    console.log('Current score:', currentScore);
    
    if (isCurrentlyLiked) {
        button.style.color = '#878a8c';
        currentScore--;
        console.log('Un-liked, new score:', currentScore);
    } else {
        button.style.color = '#ff4500';
        currentScore++;
        console.log('Liked, new score:', currentScore);
        
        if (isCurrentlyDisliked) {
            dislikeButton.style.color = '#878a8c';
            currentScore++;
            console.log('Removed dislike, final score:', currentScore);
        }
    }
    
    scoreElement.textContent = currentScore;
    
    $.ajax({
        type: 'GET',
        url: '/react_to_content',
        data: {
            post_id: postId,
            action: "like",
        },
        success: function(response) {
            console.log('Like AJAX success:', response);
        },
        error: function(xhr, status, error) {
            console.log('Like AJAX error:', error);
        }
    });
}

function handleDislikeClick(postId, buttonElement) {
    console.log('Direct dislike function called for post:', postId);
    
    var button = buttonElement;
    var isCurrentlyDisliked = button.style.color.includes('113') || button.style.color.includes('7193ff');
    console.log('Is currently disliked:', isCurrentlyDisliked);
    
    var scoreElement = button.parentElement.querySelector('span');
    var likeButton = document.getElementById('l' + postId);
    var isCurrentlyLiked = likeButton && (likeButton.style.color.includes('255') && likeButton.style.color.includes('69'));
    
    var currentScore = parseInt(scoreElement.textContent, 10);
    console.log('Current score:', currentScore);
    
    if (isCurrentlyDisliked) {
        button.style.color = '#878a8c';
        currentScore++;
        console.log('Un-disliked, new score:', currentScore);
    } else {
        button.style.color = '#7193ff';
        currentScore--;
        console.log('Disliked, new score:', currentScore);
        
        if (isCurrentlyLiked) {
            likeButton.style.color = '#878a8c';
            currentScore--;
            console.log('Removed like, final score:', currentScore);
        }
    }
    
    scoreElement.textContent = currentScore;
    
    $.ajax({
        type: 'GET',
        url: '/react_to_content',
        data: {
            post_id: postId,
            action: "dislike",
        },
        success: function(response) {
            console.log('Dislike AJAX success:', response);
        },
        error: function(xhr, status, error) {
            console.log('Dislike AJAX error:', error);
        }
    });
}

$(document).on('click','.like-button',function(e) {
    console.log('Like button clicked!');
    e.preventDefault();
    e.stopPropagation();
    
    var button = e.currentTarget;
    var elem_id = button.getAttribute('id').slice(1); // Remove 'l' prefix
    console.log('Post ID:', elem_id);
    console.log('Current button color:', button.style.color);
    
    // Simplified color detection - check if orange/red or not
    var isCurrentlyLiked = button.style.color.includes('255') && button.style.color.includes('69');
    console.log('Is currently liked:', isCurrentlyLiked);
    
    // Find the score element (sibling of the buttons)
    var scoreElement = button.parentElement.querySelector('span');
    var dislikeButton = document.getElementById(`d${elem_id}`);
    var isCurrentlyDisliked = dislikeButton && (dislikeButton.style.color.includes('113') || dislikeButton.style.color.includes('7193ff'));
    
    var currentScore = parseInt(scoreElement.textContent, 10);
    console.log('Current score:', currentScore);
    
    if (isCurrentlyLiked) {
        // Un-like: change to neutral
        button.style.color = '#878a8c';
        currentScore--;
        console.log('Un-liked, new score:', currentScore);
    } else {
        // Like: change to orange
        button.style.color = '#ff4500';
        currentScore++;
        console.log('Liked, new score:', currentScore);
        
        // If currently disliked, remove dislike
        if (isCurrentlyDisliked) {
            dislikeButton.style.color = '#878a8c';
            currentScore++; // Remove the dislike as well
            console.log('Removed dislike, final score:', currentScore);
        }
    }
    
    scoreElement.textContent = currentScore;
    
    $.ajax({
        type: 'GET',
        url: '/react_to_content',
        data: {
            post_id: elem_id,
            action: "like",
        },
        success: function(response) {
            console.log('Like AJAX success:', response);
        },
        error: function(xhr, status, error) {
            console.log('Like AJAX error:', error);
        }
    });
});


$(document).on('click','.dislike-button',function(e) {
    console.log('Dislike button clicked!');
    e.preventDefault();
    e.stopPropagation();
    
    var button = e.currentTarget;
    var elem_id = button.getAttribute('id').slice(1); // Remove 'd' prefix
    console.log('Post ID:', elem_id);
    console.log('Current button color:', button.style.color);
    
    // Simplified color detection - check if blue or not
    var isCurrentlyDisliked = button.style.color.includes('113') || button.style.color.includes('7193ff');
    console.log('Is currently disliked:', isCurrentlyDisliked);
    
    // Find the score element (sibling of the buttons)
    var scoreElement = button.parentElement.querySelector('span');
    var likeButton = document.getElementById(`l${elem_id}`);
    var isCurrentlyLiked = likeButton && (likeButton.style.color.includes('255') && likeButton.style.color.includes('69'));
    
    var currentScore = parseInt(scoreElement.textContent, 10);
    console.log('Current score:', currentScore);
    
    if (isCurrentlyDisliked) {
        // Un-dislike: change to neutral
        button.style.color = '#878a8c';
        currentScore++;
        console.log('Un-disliked, new score:', currentScore);
    } else {
        // Dislike: change to blue
        button.style.color = '#7193ff';
        currentScore--;
        console.log('Disliked, new score:', currentScore);
        
        // If currently liked, remove like
        if (isCurrentlyLiked) {
            likeButton.style.color = '#878a8c';
            currentScore--; // Remove the like as well
            console.log('Removed like, final score:', currentScore);
        }
    }
    
    scoreElement.textContent = currentScore;
    
    $.ajax({
        type: 'GET',
        url: '/react_to_content',
        data: {
            post_id: elem_id,
            action: "dislike",
        },
        success: function(response) {
            console.log('Dislike AJAX success:', response);
        },
        error: function(xhr, status, error) {
            console.log('Dislike AJAX error:', error);
        }
    });
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

