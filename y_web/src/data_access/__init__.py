"""
y_web.src.data_access — split data-access package.

Re-exports every public function from the four domain sub-modules so that
``from y_web.src.data_access import some_function`` works for all functions.

Sub-modules
-----------
profiles  — profile picture resolution (get_safe_profile_pic)
posts     — post retrieval and augmentation
users     — follower/followee and interest queries
trends    — trending hashtags, emotions, and topics
"""

# posts
from y_web.src.data_access.posts import (  # noqa: F401
    augment_text,
    get_elicited_emotions,
    get_posts_associated_to_emotion,
    get_posts_associated_to_hashtags,
    get_posts_associated_to_interest,
    get_topics,
    get_unanswered_mentions,
    get_user_recent_posts,
)

# profiles
from y_web.src.data_access.profiles import get_safe_profile_pic  # noqa: F401

# trends
from y_web.src.data_access.trends import (  # noqa: F401
    get_top_user_hashtags,
    get_trending_emotions,
    get_trending_hashtags,
    get_trending_topics,
)

# users
from y_web.src.data_access.users import (  # noqa: F401
    get_mutual_friends,
    get_user_friends,
    get_user_recent_interests,
)
