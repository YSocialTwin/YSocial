"""The per-experiment frontend settings every platform has, and the defaults of all of them.

Both the admin panel (``/admin/frontend_settings``, which validates what it saves against these keys) and the
participant pages (``routes.social.helpers._load_ui_settings``) read the same defaults (``defaults_for``), so a key
can never exist on one side only. The settings a platform owns (a feed ordering, the parameters of one of its
recommenders, the pages of an observer) are declared by its provider (``frontend_settings``) and added to these for
the experiments of that platform. Stored values are merged over the defaults at read time; no migration is needed
for a new key.
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
    "show_trending_hashtags": True,  # show the "Trending Hashtags" box (Standard feed only)
    "show_suggested_friends": True,  # show the "Suggested Friends" box (Standard / photo feeds)
    "show_recsys_info": False,  # box: the user's content recommender system, explained (Standard / photo feeds)
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
    "show_pagination_buttons": True,  # Previous/Next buttons when infinite scroll is disabled (False = one page only)
}


def declared_settings(platform_type) -> tuple:
    """The settings the providers of ``platform_type`` declare (the first declaration of a key wins)."""
    from y_web.platforms import registry

    found = {}
    for provider in registry.all_providers():
        if provider.key == platform_type:
            for setting in provider.frontend_settings:
                found.setdefault(setting.key, setting)
    return tuple(found.values())


def defaults_for(platform_type=None) -> dict:
    """Defaults of every setting an experiment of ``platform_type`` has (the common ones when ``None``)."""
    merged = dict(DEFAULT_SETTINGS)
    if platform_type:
        merged.update(
            {
                setting.key: setting.default
                for setting in declared_settings(platform_type)
            }
        )
    return merged
