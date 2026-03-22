"""Blueprint singleton and shared constants for the experiments sub-package."""
import re
import threading
from flask import Blueprint

experiments = Blueprint("experiments", __name__)


# Configuration constants
OPINION_CACHE_EXPIRY_MINUTES = 5  # Cache expiry time for opinion evolution statistics
MAX_HPC_PER_GROUP = 4  # Maximum number of HPC experiments allowed per schedule group
DEFAULT_FEED_LIMITS = {
    "rss_entries_per_feed": 100,
    "reddit_entries_per_feed": 200,
    "reddit_pages": 2,
    "reddit_rate_limit_seconds": 2,
    "db_fallback_limit": 50,
    "image_entries_per_feed": 100,
}
DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS = {
    "service": "",
    "host": "",
    "model": "",
}
DEFAULT_FORUM_EMBEDDING_SETTINGS = dict(DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS)
DEFAULT_FORUM_AVATAR_SETTINGS = {
    "mode": "placeholder",
}

FORUM_FEED_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}

# Lock to prevent concurrent schedule advancement (from HTTP endpoint and background monitor)
_schedule_check_lock = threading.Lock()
_EXP_IDS_MARKER_RE = re.compile(r"\[exp_ids:([0-9,\s]+)\]")


