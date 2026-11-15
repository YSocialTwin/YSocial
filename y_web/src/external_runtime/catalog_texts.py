"""Descriptions of the built-in plugin catalogue (``builtin_plugins.json``) that are translated in the core catalogue.

The catalogue of installable repositories names them, so their texts are declared here for extraction; a platform that
is installed later brings its own description in ``meta/info.json`` and its own translation domain.
"""

from y_web.i18n import N_

PLATFORM_TEXTS = (
    N_(
        "Legacy microblogging simulator on Flask (timeline, posts, follows). Server and client are installed and updated independently from its page."
    ),
    N_(
        "Legacy forum simulator on Flask (threads and replies). Server and client are installed and updated independently from its page."
    ),
    N_("Runs the agents of a microblogging simulation (client side)."),
    N_("Hosts the microblogging platform the agents interact with (server side)."),
    N_("Runs the agents of a forum simulation (client side)."),
    N_("Hosts the forum platform the agents interact with (server side)."),
    N_(
        "Simulation runtime for photo-sharing experiments, with an Instagram-like platform."
    ),
    N_(
        "Simulation runtime for instant-messaging experiments, with Telegram-like chats, groups, channels and forum topics."
    ),
    N_(
        "Simulation runtime for Tinder-like dating experiments: profiles, swipes, mutual matches, private conversations and interchangeable matching recommenders."
    ),
    N_(
        "Ray-based runtime for microblogging experiments (posts, timelines, follows) built for large-scale simulations, on a single machine or on HPC clusters."
    ),
    N_(
        "Ray runtime for Reddit-style forum experiments: threads, comments, votes, follows and interchangeable content recommenders on HPC clusters."
    ),
)
