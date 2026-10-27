"""The one table of per-experiment frontend settings and their defaults.

Both the admin panel (``/admin/frontend_settings``, which validates what it saves against these keys) and the
participant pages (``routes.social.helpers._load_ui_settings``) read this table, so a key can never exist on one
side only. Stored values are merged over these defaults at read time; no migration is needed for a new key.
"""

DEFAULT_SETTINGS = {
    # Interactions
    "interactions_enabled": True,
    "interaction_post": True,
    "interaction_comment": True,
    "interaction_like": True,
    "interaction_dislike": True,
    "interaction_share": True,
    "notifications_menu": True,  # Bell / mentions icon, shown alongside interactions in the admin UI
    # Annotations
    "annotations_enabled": True,
    "annotation_emotions": True,
    "annotation_topics": True,
    "annotation_sentiment": True,
    "annotation_toxicity": True,
    "annotation_agent_type": True,
    "annotation_author_type": True,
    "show_post_time": True,  # show "Day X - HH:00" below each post/comment
    "show_trending_hashtags": True,  # show the "Trending Hashtags" box (microblogging only)
    "show_suggested_friends": True,  # show the "Suggested Friends" box (microblogging / photo)
    "show_recsys_info": False,  # box: the user's content recommender system, explained (microblogging / photo)
    # Interface language of the participant pages (decision D4: set per experiment)
    "language": "",  # empty = the default language (English); otherwise a supported code
    "language_switch_allowed": False,  # let participants pick another language (cookie ys_lang_sim)
    "show_annotation_stats": False,  # box: live distributions of the user's annotations (needs the annotation add-on)
    # Feed & Profile
    "default_content_recsys": "",  # empty = system default
    "default_follow_recsys": "",  # empty = system default
    "profile_topics_box": True,  # show Topics & Opinions card in edit_profile
    "onboarding_enabled": True,  # show onboarding screen on first login
    # Infinite scroll & pagination
    "infinite_scroll_enabled": True,  # enable infinite scroll (False = paginate)
    "posts_per_page": 10,  # posts per page when infinite scroll is disabled
    # Platform-specific feed defaults (forum / photo sharing)
    "default_forum_feed_type": "new",  # new | hot | top | most_commented
    "default_photo_feed_tab": "for_you",  # for_you | follower
    # FilterBubble (Personalized Feed) recommender parameters
    "filter_bubble_alpha": 2.0,  # opinion similarity width (Gaussian)
    "filter_bubble_beta": 0.0,  # recency decay (0 = disabled)
    "filter_bubble_gamma": 0.0,  # engagement amplification (0 = disabled)
    "filter_bubble_lr": 0.05,  # EMA learning rate for real-time interest update
    "filter_bubble_sort": "score",  # ranking mode: score | recency | engagement | hybrid
    "filter_bubble_wr": 1.0,  # weight for reactions in engagement score
    "filter_bubble_wc": 1.5,  # weight for comments in engagement score
    "filter_bubble_ws": 2.0,  # weight for shares in engagement score
}
