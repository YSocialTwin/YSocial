"""How a username is shown to people in the microblogging frontend.

Agent usernames are camel case (``MariaRossi``, ``Sig.RiccardoFagiani``). Where a *name* is displayed the words
are separated with a space (``Maria Rossi``, ``Sig. Riccardo Fagiani``). Tags (``@username`` mentions, hashtags),
links and form values keep the real username, so this is applied only to the text of a displayed name.
"""

import re

_LOWER_TO_UPPER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_TO_WORD = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_DOT_TO_WORD = re.compile(r"(?<=\.)(?=[A-Z])")


def display_name(value):
    """``value`` with the words of a camel case username separated by spaces; anything else is returned as is."""
    if not isinstance(value, str) or " " in value or "@" in value or "#" in value:
        return value
    text = _DOT_TO_WORD.sub(" ", value)
    text = _LOWER_TO_UPPER.sub(" ", text)
    return _ACRONYM_TO_WORD.sub(" ", text)
