"""Parameters of a World Simulation as explicit form fields (no JSON editing in the interface).

Every user-meaningful option of ``federation.json`` has a :class:`Param` here: its place in the form, label, help text, SDK
default and limits. The same table drives

* the form (``admin/world_simulation/_options_form.html`` renders it),
* the reading of a submitted form into the stored options (:func:`apply_form`) and
* the validation (:func:`validate`), which repeats the checks the coordinator makes at start so that a wrong value is
  refused with a clear message instead of stopping the run.

Round trip rules (the stored options stay what they were unless the person changes a value):

* a value that equals the SDK default is **not written** (unset stays unset, so ``federation.json`` is as before);
* a key that is already stored and whose submitted value is unchanged is left exactly as it is, even if it equals the default;
* a blank number removes the key (the SDK default applies);
* keys the form does not cover (other blocks' keys, ``beta`` entries of a later release, ...) are never dropped.

Labels and help texts are marked with ``N_`` and translated when rendered or reported.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Optional

from y_web.i18n import N_
from y_web.i18n import gettext as _

MISSING = object()

CROSSPOST_CONTENT = ("own_content", "news", "images")
CROSSPOST_CONTENT_ALIASES = {"own_posts": "own_content"}
# Platforms of a World Simulation: the member of each platform is called as the platform type.
PLATFORMS = ("microblogging", "forum", "photo_sharing", "instant_messaging", "dating")
# Platforms whose runtime creates an account on request (service.PROVISIONABLE, repeated here to stay import free).
PROVISIONABLE = ("microblogging",)
MEMBERSHIP_CHOICES = ("all", "one_random", "custom")


@dataclass(frozen=True)
class Param:
    path: tuple  # key path inside the stored options, e.g. ("attention", "temperature")
    kind: str  # bool | int | float | choice
    default: Any
    label: str
    help: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    min_exclusive: bool = False
    choices: tuple = ()  # ((value, label), ...) for kind == "choice"
    advanced: bool = False
    legacy_name: str = ""  # form name used by earlier pages (kept so that older posts keep working)

    @property
    def block(self) -> str:
        return self.path[0]

    @property
    def name(self) -> str:
        return self.legacy_name or "opt__" + "__".join(self.path)

    @property
    def dotted(self) -> str:
        return ".".join(self.path)


def _p(block, key, kind, default, label, help="", **kw):
    return Param((block, key), kind, default, label, help, **kw)


# --------------------------------------------------------------------------------------------------------- the table
ATTENTION = (
    Param(("attention", "enabled"), "bool", False, N_("Share the daily attention of each agent among its platforms"),
          N_("Every day each agent splits its activity among the platforms where it is active, according to how rewarding "
             "they were. Off: every agent keeps its own activity on each platform."), legacy_name="attention_enabled"),
    _p("attention", "temperature", "float", 1.0, N_("Temperature"),
       N_("How sharply the agent favours its best platform. Low values concentrate attention, high values spread it evenly. Greater than 0."),
       minimum=0.0, min_exclusive=True, advanced=True),
    _p("attention", "inertia", "float", 0.3, N_("Inertia"),
       N_("Weight of the previous day: 0 follows only the latest day, 1 never changes the shares. Between 0 and 1."),
       minimum=0.0, maximum=1.0, advanced=True),
    _p("attention", "min_multiplier", "float", 0.1, N_("Smallest multiplier"),
       N_("Lowest factor applied to an agent's chance of a session on a platform. At least 0."), minimum=0.0, advanced=True),
    _p("attention", "max_multiplier", "float", 3.0, N_("Largest multiplier"),
       N_("Highest factor applied to an agent's chance of a session on a platform. Not below the smallest multiplier."),
       minimum=0.0, advanced=True),
    _p("attention", "normalization", "choice", "raw", N_("Comparison of platforms"),
       N_("How the reward of different platforms is compared before sharing attention."),
       choices=(("raw", N_("Native values")), ("zscore", N_("Standardised per platform (z-score)"))), advanced=True),
)
LEAVE = (
    Param(("leave", "enabled"), "bool", False, N_("Agents leave platforms that no longer interest them"),
          N_("An agent leaves a platform when its share of attention there stays low for several days, as long as it stays "
             "active somewhere else. Needs the attention sharing above."), legacy_name="leave_enabled"),
    _p("leave", "weight_threshold", "float", 0.1, N_("Attention share below which an agent is losing interest"),
       N_("Between 0 and 1."), minimum=0.0, maximum=1.0, advanced=True),
    _p("leave", "consecutive_days", "int", 3, N_("Days in a row before leaving"), N_("At least 1."), minimum=1, advanced=True),
)
DISCOVERY = (
    Param(("discovery", "enabled"), "bool", False, N_("Agents discover and join new platforms"),
          N_("Agents become aware of a platform from what they see of it (cross-posts) and may open an account there. "
             "Switching it on also makes the platforms report what each agent was shown."), legacy_name="discovery_enabled"),
    _p("discovery", "decision", "choice", "logit", N_("Decision rule"),
       N_("How an aware agent decides to join: a probability that grows with awareness, ties, interest and frustration "
          "(logistic), or a fixed probability once awareness passes the threshold."),
       choices=(("logit", N_("Logistic (graded)")), ("threshold", N_("Fixed probability"))), advanced=False),
    _p("discovery", "max_active_platforms", "int", 5, N_("Most platforms an agent can be active on"),
       N_("At least 1; there are at most five platforms."), minimum=1, advanced=False),
    _p("discovery", "rejoin_cooldown_days", "int", 14, N_("Days before an agent can rejoin a platform it left"),
       N_("0 or more."), minimum=0, advanced=False),
    _p("discovery", "decay", "float", 0.1, N_("Daily decay of awareness"),
       N_("Share of awareness lost every day. Between 0 and 1."), minimum=0.0, maximum=1.0, advanced=True),
    _p("discovery", "w_view", "float", 1.0, N_("Weight of a view"), N_("Awareness added by seeing content of the platform."), advanced=True),
    _p("discovery", "w_view_tie", "float", 2.0, N_("Weight of a view from someone followed"),
       N_("Awareness added when the author is followed by the agent."), advanced=True),
    _p("discovery", "w_interact", "float", 3.0, N_("Weight of an interaction"),
       N_("Awareness added by interacting with content of the platform."), advanced=True),
    _p("discovery", "window_days", "int", 7, N_("Days observed"),
       N_("Window used to count the followed authors seen on a platform. At least 1."), minimum=1, advanced=True),
    _p("discovery", "aware_threshold", "float", 3.0, N_("Awareness needed to consider joining"),
       N_("An agent is eligible to join once its awareness reaches this value."), advanced=True),
    _p("discovery", "base_rate", "float", 0.0, N_("Background awareness rate"),
       N_("Chance per day of becoming aware without any exposure. Between 0 and 1."), minimum=0.0, maximum=1.0, advanced=True),
    _p("discovery", "social_cap", "int", 5, N_("Cap on social evidence"),
       N_("Followed authors counted at most. 0 or more."), minimum=0, advanced=True),
    _p("discovery", "threshold_probability", "float", 0.5, N_("Probability of joining (fixed rule)"),
       N_("Used only with the fixed probability rule. Between 0 and 1."), minimum=0.0, maximum=1.0, advanced=True),
    _p("discovery", "quoted_weight", "float", 0.0, N_("Awareness credit for the platform of quoted content"),
       N_("Share of the exposure weight credited to the platform where a quoted content lives. 0 switches it off. Between 0 and 1."),
       minimum=0.0, maximum=1.0, advanced=True),
)
BETA_KEYS = (("0", N_("Intercept")), ("A", N_("Awareness")), ("S", N_("Social evidence")), ("I", N_("Interest")),
             ("N", N_("Number of active platforms")), ("F", N_("Frustration")))
BETA_DEFAULTS = {"0": -3.0, "A": 1.0, "S": 0.5, "I": 1.5, "N": 0.5, "F": 0.5}
BETA = tuple(Param(("discovery", "beta", k), "float", BETA_DEFAULTS[k], label, advanced=True) for k, label in BETA_KEYS)
CROSSPOST = (
    Param(("crosspost", "mode"), "choice", "coordinator_rule", N_("Who decides the cross-posts"),
          N_("By rule: the coordinator copies content to other platforms with the probabilities below. By the agent: each agent "
             "chooses where to post, with the propensity below."),
          choices=(("coordinator_rule", N_("The coordinator, by rule")), ("agent_action", N_("The agent, by its own action")))),
    Param(("crosspost", "propensity"), "float", 0.0, N_("Propensity to cross-post"),
          N_("Probability that an agent marks a post for cross-posting (by rule) or posts on another platform (by agent action). "
             "0 means never. Between 0 and 1."), minimum=0.0, maximum=1.0),
)
TOPICS = (
    Param(("topics", "migration"), "bool", True, N_("Shared content brings its topics, and missing topics are created"),
          N_("On by default: content that crosses a platform carries its topics and the destination creates the ones it lacks."),
          legacy_name="topic_migration"),
)
PSEUDONYMS = (
    Param(("pseudonyms", "enabled"), "bool", False, N_("Use pseudonyms for authors in cross-posts"),
          N_("The platforms that receive a quoted post see a stable pseudonym instead of the name of its author."),
          legacy_name="pseudonyms_enabled"),
)

PARAMS = ATTENTION + LEAVE + DISCOVERY + BETA + CROSSPOST + TOPICS + PSEUDONYMS
BY_NAME = {p.name: p for p in PARAMS}
BY_PATH = {p.path: p for p in PARAMS}
# Boolean switches without a presence marker: an absent checkbox means off (as in earlier pages).
# ``topics.migration`` has a hidden marker (``topics_present``) because it is on by default.
PRESENCE = {("topics", "migration"): "topics_present"}

# Keys covered by the form besides the table (blocks of their own handling).
SPECIAL_PATHS = {("crosspost", "content"), ("crosspost", "probability"), ("membership", "initial"), ("provisioning", "members")}
COVERED = {p.path for p in PARAMS} | SPECIAL_PATHS

SECTIONS = (
    {"id": "attention", "title": N_("Attention"),
     "intro": N_("How the daily activity of an agent is shared among the platforms where it is active, and when it leaves one."),
     "groups": (ATTENTION, LEAVE)},
    {"id": "discovery", "title": N_("Discovery"),
     "intro": N_("Whether agents find out about the other platforms and join them while the World Simulation runs."),
     "groups": (DISCOVERY,)},
)


def basic(params):
    return [p for p in params if not p.advanced]


def advanced(params):
    return [p for p in params if p.advanced]


# ----------------------------------------------------------------------------------------------------- value helpers
def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def _get(options, path, default=MISSING):
    node = options
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _set(options, path, value):
    node = options
    for key in path[:-1]:
        if not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    node[path[-1]] = value


def _remove(options, path):
    """Delete a key and the dicts that became empty because of it (never one that was empty before)."""
    chain = [options]
    for key in path[:-1]:
        nxt = chain[-1].get(key) if isinstance(chain[-1], dict) else None
        if not isinstance(nxt, dict):
            return
        chain.append(nxt)
    if path[-1] not in chain[-1]:
        return
    del chain[-1][path[-1]]
    for depth in range(len(path) - 2, -1, -1):
        if chain[depth + 1] == {}:
            del chain[depth][path[depth]]
        else:
            break


def fmt(value) -> str:
    """A number as the person would type it."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return repr(value) if isinstance(value, float) else str(value)


def _g(value) -> str:
    return "%g" % value


# ------------------------------------------------------------------------------------------------ options -> form values
def values_from_options(options) -> dict:
    """Form values (name -> string, bool or list) for a stored options dict: stored value, else the SDK default."""
    options = options or {}
    out = {}
    for p in PARAMS:
        stored = _get(options, p.path)
        value = p.default if stored is MISSING else stored
        out[p.name] = bool(value) if p.kind == "bool" else (value if p.kind == "choice" else fmt(value))
    content = (options.get("crosspost") or {}).get("content") or []
    names = {CROSSPOST_CONTENT_ALIASES.get(c, c) for c in content if isinstance(c, str)}
    out["crosspost_content"] = [] if ("all" in names or not names) else [c for c in CROSSPOST_CONTENT if c in names]
    probability = (options.get("crosspost") or {}).get("probability") or {}
    for src in PLATFORMS:
        for dst in PLATFORMS:
            if src != dst:
                v = probability.get(f"{src}->{dst}")
                out[f"prob__{src}__{dst}"] = "" if v is None else fmt(v)
    initial = (options.get("membership") or {}).get("initial", "all")
    out["membership_initial"] = "custom" if isinstance(initial, dict) else (initial if initial in MEMBERSHIP_CHOICES else "all")
    for m in PLATFORMS:
        v = initial.get(m) if isinstance(initial, dict) else None
        out[f"membership_p__{m}"] = "" if v is None else fmt(v)
    out["provisioning_members"] = [m for m in PROVISIONABLE if m in ((options.get("provisioning") or {}).get("members") or [])]
    return out


def values_from_form(form) -> dict:
    """The submitted values again (to show the form after a refusal, with what the person typed)."""
    out = values_from_options({})
    for p in PARAMS:
        if p.kind == "bool":
            marker = PRESENCE.get(p.path)
            out[p.name] = bool(form.get(p.name)) if marker is None or form.get(marker) else p.default
        elif p.name in form:
            out[p.name] = form.get(p.name)
    if form.get("crosspost_content_present"):
        chosen = [CROSSPOST_CONTENT_ALIASES.get(v, v) for v in form.getlist("crosspost_content")]
        out["crosspost_content"] = [c for c in CROSSPOST_CONTENT if c in chosen] if "all" not in chosen else []
    for key in form.keys():
        if key.startswith(("prob__", "membership_p__")):
            out[key] = form.get(key, "")
    if "membership_initial" in form:
        out["membership_initial"] = form.get("membership_initial")
    if form.get("provisioning_present"):
        out["provisioning_members"] = [m for m in form.getlist("provisioning_members") if m in PROVISIONABLE]
    return out


def unknown_paths(options) -> list:
    """Dotted names of stored keys the form does not cover (they are kept as they are)."""
    found = []

    def walk(node, prefix):
        for key, value in sorted((node or {}).items()):
            path = prefix + (key,)
            if key == "exposures" and not prefix:
                continue
            if path in COVERED:
                continue
            if isinstance(value, dict) and any(p[: len(path)] == path for p in COVERED):
                walk(value, path)
            else:
                found.append(".".join(path))

    walk(options if isinstance(options, dict) else {}, ())
    return found


# ------------------------------------------------------------------------------------------------ form -> options
def _number(p: Param, text, errors):
    text = (text or "").strip() if isinstance(text, str) else text
    if text in ("", None):
        return None
    try:
        if p.kind == "int":
            number = float(text)
            if number != int(number):
                raise ValueError
            return int(number)
        return float(text)
    except (TypeError, ValueError):
        errors.append(_("%(label)s must be %(kind)s.", label=_(p.label), kind=_("an integer") if p.kind == "int" else _("a number")))
        return MISSING


def _store(options, base, path, value, default):
    """Apply one submitted value following the round trip rules."""
    stored = _get(base, path)
    if value is None:  # blank: SDK default
        _remove(options, path)
    elif stored is not MISSING and _same(stored, value):
        pass  # unchanged: leave the stored text of the key as it is
    elif _same(value, default):
        _remove(options, path)
    else:
        _set(options, path, value)


def apply_form(form, base=None, members=None):
    """Read a submitted form over the stored options ``base`` (without ``exposures``).

    Returns ``(options, errors)``: ``errors`` is a list of messages (empty when the form is valid). ``members`` are the platform
    types of the World Simulation: the probabilities and the starting map keep only those."""
    base = copy.deepcopy(base) if isinstance(base, dict) else {}
    options = copy.deepcopy(base)
    errors: list = []
    for p in PARAMS:
        marker = PRESENCE.get(p.path)
        if p.kind == "bool":
            if marker and not form.get(marker):
                continue  # an older page without the control leaves the setting alone
            _store(options, base, p.path, bool(form.get(p.name)), p.default)
        elif p.name not in form:
            continue
        elif p.kind == "choice":
            value = form.get(p.name)
            if value not in [c[0] for c in p.choices]:
                errors.append(_("Choose a valid option for %(label)s.", label=_(p.label)))
                continue
            _store(options, base, p.path, value, p.default)
        else:
            value = _number(p, form.get(p.name), errors)
            if value is MISSING:
                continue
            _store(options, base, p.path, value, p.default)
    _apply_probability(form, base, options, members, errors)
    _apply_membership(form, base, options, members, errors)
    _apply_provisioning(form, base, options)
    _apply_content(form, options, errors)
    errors.extend(validate(options))
    errors.extend(check_dependencies(options))
    return options, list(dict.fromkeys(errors))


def _apply_probability(form, base, options, members, errors):
    for key in form.keys():
        if not key.startswith("prob__"):
            continue
        parts = key.split("__")
        if len(parts) != 3 or parts[1] == parts[2]:
            continue
        src, dst = parts[1], parts[2]
        if members is not None and (src not in members or dst not in members):
            continue
        label = f"{src}->{dst}"
        probe = Param(("crosspost", "probability", label), "float", 0.0, _("Probability %(pair)s", pair=label))
        value = _number(probe, form.get(key), errors)
        if value is MISSING:
            continue
        _store(options, base, probe.path, value, 0.0)


def _apply_membership(form, base, options, members, errors):
    choice = form.get("membership_initial")
    if choice is None:
        return
    path = ("membership", "initial")
    if choice not in MEMBERSHIP_CHOICES:
        errors.append(_("Choose a valid option for %(label)s.", label=_("Starting state of the agents")))
        return
    stored = _get(base, path)
    if choice == "all":
        if stored != "all":  # an explicit "all" already stored stays as it is
            _remove(options, path)
    elif choice == "one_random":
        if stored != "one_random":
            _set(options, path, "one_random")
    else:
        mapping = dict(stored) if isinstance(stored, dict) else {}
        for key in form.keys():
            if not key.startswith("membership_p__"):
                continue
            member = key.split("__", 1)[1]
            if members is not None and member not in members:
                continue
            probe = Param(("membership", "initial", member), "float", 0.0, _("Probability of starting on %(platform)s", platform=member))
            value = _number(probe, form.get(key), errors)
            if value is MISSING:
                continue
            if value is None:
                mapping.pop(member, None)
            elif member not in mapping or not _same(mapping[member], value):
                mapping[member] = value
        if members is not None:
            mapping = {m: v for m, v in mapping.items() if m in members}
        if not mapping:
            errors.append(_("Give the probability of starting on at least one platform, or choose another starting state."))
        else:
            _set(options, path, mapping)


def _apply_provisioning(form, base, options):
    if not form.get("provisioning_present"):
        return
    chosen = [m for m in form.getlist("provisioning_members") if m in PROVISIONABLE]
    stored = (_get(base, ("provisioning", "members"), []) or [])
    kept = [m for m in stored if isinstance(m, str) and m not in PROVISIONABLE]  # members this page cannot show stay
    members = [m for m in PROVISIONABLE if m in chosen] + kept
    if members == stored:
        return
    if members:
        _set(options, ("provisioning", "members"), members)
    else:
        _remove(options, ("provisioning", "members"))


def _apply_content(form, options, errors):
    if not form.get("crosspost_content_present"):
        return
    chosen = [CROSSPOST_CONTENT_ALIASES.get(v, v) for v in form.getlist("crosspost_content")]
    if not chosen:
        errors.append(_("Choose All content, or at least one kind of content that may be cross-posted."))
        return
    form_content = [c for c in ("all",) + CROSSPOST_CONTENT if c in chosen]
    crosspost = {k: v for k, v in (options.get("crosspost") or {}).items() if k != "content"}
    if form_content != ["all"]:  # all content is the default: not stored (a mix with "all" is refused by the validation)
        crosspost["content"] = form_content
    if crosspost:
        options["crosspost"] = crosspost
    else:
        options.pop("crosspost", None)


# ----------------------------------------------------------------------------------------------------- validation
def _range_message(p: Param) -> str:
    if p.minimum is not None and p.maximum is not None:
        return _("%(label)s must be between %(low)s and %(high)s.", label=_(p.label), low=_g(p.minimum), high=_g(p.maximum))
    if p.min_exclusive:
        return _("%(label)s must be greater than %(low)s.", label=_(p.label), low=_g(p.minimum))
    return _("%(label)s must be at least %(low)s.", label=_(p.label), low=_g(p.minimum))


def validate(options) -> list:
    """Messages for the stored values the coordinator would refuse at start (only known keys are looked at)."""
    errors = []
    for p in PARAMS:
        value = _get(options, p.path)
        if value is MISSING or p.kind == "bool":
            continue
        if p.kind == "choice":
            if value not in [c[0] for c in p.choices]:
                errors.append(_("Choose a valid option for %(label)s.", label=_(p.label)))
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(_("%(label)s must be %(kind)s.", label=_(p.label), kind=_("a number")))
            continue
        if p.kind == "int" and number != int(number):
            errors.append(_("%(label)s must be %(kind)s.", label=_(p.label), kind=_("an integer")))
        elif (p.minimum is not None and (number < p.minimum or (p.min_exclusive and number == p.minimum))) or (
                p.maximum is not None and number > p.maximum):
            errors.append(_range_message(p))
    attention = options.get("attention") or {}
    if isinstance(attention, dict) and _numbers(attention, "min_multiplier", "max_multiplier") and float(
            attention.get("min_multiplier", 0.1)) > float(attention.get("max_multiplier", 3.0)):
        errors.append(_("The largest multiplier cannot be smaller than the smallest."))
    crosspost = options.get("crosspost") or {}
    probability = crosspost.get("probability") if isinstance(crosspost, dict) else None
    if probability is not None:
        if not isinstance(probability, dict):
            errors.append(_("The cross-post probabilities must be an object."))
        else:
            for key, value in probability.items():
                try:
                    ok = "->" in str(key) and 0.0 <= float(value) <= 1.0
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    errors.append(_("The probability %(pair)s must be between 0 and 1.", pair=str(key)))
    initial = (options.get("membership") or {}).get("initial", "all") if isinstance(options.get("membership"), dict) else "all"
    if isinstance(initial, dict):
        for key, value in initial.items():
            try:
                ok = 0.0 <= float(value) <= 1.0
            except (TypeError, ValueError):
                ok = False
            if not ok:
                errors.append(_("The probability of starting on %(platform)s must be between 0 and 1.", platform=str(key)))
    elif initial not in ("all", "one_random"):
        errors.append(_("Choose a valid option for %(label)s.", label=_("Starting state of the agents")))
    return errors


def _numbers(section, *keys) -> bool:
    for key in keys:
        if key in section:
            try:
                float(section[key])
            except (TypeError, ValueError):
                return False
    return True


def check_dependencies(options) -> list:
    """Combinations the coordinator refuses (only checked when the form is read)."""
    if (_get(options, ("leave", "enabled"), False) is True or _get(options, ("leave", "enabled"), False) == 1) and not _get(
            options, ("attention", "enabled"), False):
        return [_("The leave rule needs the attention sharing: switch Attention on, or switch Leave off.")]
    return []


def default_options() -> dict:
    """Every parameter at its SDK default (documentation and tests)."""
    out: dict = {}
    for p in PARAMS:
        _set(out, p.path, p.default)
    return out
