"""
Frontend Settings admin route.

Allows administrators to configure UI parameters per experiment of any
supported platform; the panel shows only
the settings that exist in the chosen platform's templates (see
``frontend_capabilities`` of each platform provider).
Settings are stored in ExpFrontendSettings (one JSON row per experiment).

Also serves the generic, repo_key-parameterized "frontend plugin suite"
panel (any installed repo registered with group="frontend_plugins" in
SUPPORTED_EXTERNAL_REPOS -- today Frontend Adds-on and Reactive Agents),
letting each such suite's modules be enabled/configured per experiment
without any suite-specific route or template code.
"""

import json

from flask import jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import N_, available_languages
from y_web.i18n import gettext as _
from y_web.platforms import registry
from y_web.src.models import ExpFrontendSettings, Exps
from y_web.src.models.config import Content_Recsys, Follow_Recsys
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments


# ------------------------------------------------------------------
# Supported platforms and what each one's templates actually offer
# ------------------------------------------------------------------
def supported_platforms():
    """Platform types that have frontend settings, in menu order."""
    return tuple(registry.keys())


def _localized_options(items):
    """Copy of ``[{"name", "label"}]`` with the labels translated for this request."""
    options = []
    for item in items:
        text = item["label"]  # declared with N_ above
        options.append({**item, "label": _(text)})
    return options


def _localized_platform_label(value):
    text = registry.resolve(value).label  # declared with N_ in the provider
    return _(text)


def _declared_keys(platform_type) -> frozenset:
    return frozenset(setting.key for setting in declared_settings(platform_type))


def _frontend_wording(platform_type: str) -> dict:
    """What the page words differently for this platform, as its provider declares it (translated here)."""
    provider = registry.get(platform_type)
    if provider is None:
        return {}
    return {
        "labels": {
            key: [_(label), _(hint)]
            for key, (label, hint) in provider.frontend_labels.items()
        },
        "annotations_hint": (
            _(provider.frontend_annotations_hint)
            if provider.frontend_annotations_hint
            else ""
        ),
        "standard_feed": provider.standard_feed,
        "infinite_scroll": provider.infinite_scroll,
    }


def capabilities_for(platform_type: str):
    """Sorted list of setting keys the platform supports, or ``None`` for all."""
    provider = registry.get(platform_type)
    caps = provider.frontend_capabilities if provider else None
    if caps is None:
        return None
    return sorted(set(caps) | _declared_keys(platform_type))


def excluded_capabilities_for(platform_type: str):
    """Setting keys to hide for a platform that otherwise offers everything."""
    provider = registry.get(platform_type)
    if provider is None or provider.frontend_capabilities is not None:
        return []
    # the settings that only some other platform's pages read
    own = _declared_keys(platform_type)
    others = set()
    for other in registry.providers():
        if other.key == platform_type:
            continue
        others |= set(other.frontend_exclusive_settings)
        others |= _declared_keys(other.key)
    return sorted(others - own)


# ------------------------------------------------------------------
# Default settings: one source shared with the participant pages
# ------------------------------------------------------------------
from y_web.src.experiment.frontend_defaults import (  # noqa: E402
    DEFAULT_SETTINGS,
    declared_settings,
    defaults_for,
)


def _language_choices() -> set:
    """Values accepted for the ``language`` setting: empty (default) or a supported language."""
    from y_web.i18n import supported_languages

    return {""} | set(supported_languages())


def _load_settings(exp_id: int) -> dict:
    exp = db.session.get(Exps, exp_id)
    defaults = defaults_for(exp.platform_type if exp else None)
    row = db.session.get(ExpFrontendSettings, exp_id)
    if row is None:
        return defaults
    try:
        loaded = json.loads(row.settings_json or "{}")
    except Exception:
        loaded = {}
    merged = dict(defaults)
    merged.update(loaded)
    return merged


def _platform_setting_specs(platform_type) -> list:
    """What the page needs to show and read the settings the platform owns (labels translated for this request)."""
    return [
        {
            "key": setting.key,
            "type": _setting_type(setting.default),
            "default": setting.default,
            "choices": _localized_options(setting.choices),
        }
        for setting in declared_settings(platform_type)
    ]


def _setting_type(default) -> str:
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "float"
    return "str"


# Labels and categories of the recommender systems come from the database seed
# (``content_recsys`` / ``follow_recsys``). They are declared here so they can be
# translated; the algorithm names stay the stable identifiers.
_RECSYS_TEXTS = (
    N_("Random"),
    N_("(RC) Reverse Chrono"),
    N_("(RCP) Popularity"),
    N_("(RCF) Followers"),
    N_("(FP) Followers-Popularity"),
    N_("(RCC) Reverse Chrono Comments"),
    N_("(CI) Common Interests"),
    N_("(CUI) Common User Interests"),
    N_("(SIR) Similar Users Reactions"),
    N_("(SIP) Similar Users Posts"),
    N_("(HLR) Hybrid Linear Ranker"),
    N_("Personalized Feed"),
    N_("Common Neighbors"),
    N_("Preferential Attachment"),
    N_("Activity"),
    N_("Global"),
    N_("Social Timeline"),
    N_("Content-Based Filtering"),
    N_("Profile-Based User Similarity"),
    N_("Behavioral User Modeling"),
    N_("Demographic-Based"),
    N_("Collaborative Filtering"),
    N_("Hybrid Models"),
    N_("Ensemble"),
    N_("Personalization"),
    N_("Baseline & Exploration"),
    N_("Local Triadic Closure"),
    N_("Popularity & Activity Bias"),
    N_("Profile & Attribute Homophily"),
    N_("Behavioral Homophily"),
    N_("Graph Proximity"),
    N_("Community Approximation"),
    N_("Other"),
)


def _recsys_text(text):
    """Translate a recommender label/category (unchanged when it has no translation)."""
    return _(text) if text in _RECSYS_TEXT_SET else text


_RECSYS_TEXT_SET = frozenset(_RECSYS_TEXTS)


def _load_recsys_options(
    simulator_type: str = "Standard",
    all_algorithms: bool = False,
    include_human_only: bool = False,
):
    """Return content and follow recsys lists, filtered by experiment type.

    For HPC experiments all algorithms are shown; for Standard experiments
    only those whose ``enabled`` column contains 'Standard' are included.

    Pass ``all_algorithms=True`` (admin configuration context) to return every
    row that has a non-empty ``enabled`` value, regardless of experiment type.
    Pass ``include_human_only=True`` to also include rows with enabled='HumanOnly'
    (the personalised feed of the human profiles).
    """
    is_hpc = (simulator_type or "").upper() == "HPC"

    def _to_list(model):
        rows = db.session.scalars(select(model).order_by(model.id.asc())).all()
        result = []
        for r in rows:
            if not r.enabled:
                continue
            enabled_lc = (r.enabled or "").lower()
            is_human_only = "humanonly" in enabled_lc
            if all_algorithms:
                include = True
            elif is_human_only:
                include = include_human_only
            elif is_hpc:
                include = "hpc" in enabled_lc
            else:
                include = "standard" in enabled_lc
            if include:
                result.append(
                    {
                        "name": r.name,
                        "label": _recsys_text(r.value),
                        "category": _recsys_text(r.category or "Other"),
                    }
                )
        return result

    return {
        "content": _to_list(Content_Recsys),
        "follow": _to_list(Follow_Recsys),
    }


# ------------------------------------------------------------------
# GET /admin/frontend_settings  — page shell
# ------------------------------------------------------------------
@experiments.route("/admin/frontend_settings", methods=["GET"])
@login_required
def frontend_settings():
    check_privileges(current_user.username)

    exps = db.session.scalars(
        select(Exps)
        .filter(Exps.platform_type.in_(supported_platforms()))
        .order_by(Exps.exp_name.asc())
    ).all()

    exps_json = json.dumps(
        [
            {
                "id": e.idexp,
                "name": e.exp_name,
                "type": e.platform_type,
                "group": (e.exp_group or "").strip(),
            }
            for e in exps
        ]
    )
    platforms_json = json.dumps(
        [
            {"value": value, "label": _localized_platform_label(value)}
            for value in supported_platforms()
        ]
    )

    recsys = _load_recsys_options(all_algorithms=True)
    recsys_json = json.dumps(recsys)

    from y_web.src.external_runtime.frontend_plugins import frontend_plugin_repo_keys
    from y_web.src.external_runtime.registry import (
        runtime_installed_and_visible,
        runtime_spec,
    )

    frontend_plugin_suites = []
    for repo_key in frontend_plugin_repo_keys():
        try:
            spec = runtime_spec(repo_key)
        except KeyError:
            continue
        # A private suite must stay hidden here too -- same gate as the
        # Plugins catalog page, not just "is it installed" (user-reported
        # 2026-10-08: installed private plugins stayed visible without
        # --development).
        if not runtime_installed_and_visible(repo_key, current_user):
            continue
        from y_web.src.external_runtime.plugin_i18n import localize_text

        frontend_plugin_suites.append(
            {"repo_key": repo_key, "label": localize_text(repo_key, spec.label)}
        )

    return render_template(
        "admin/frontend_settings.html",
        exps_json=exps_json,
        platforms_json=platforms_json,
        recsys_json=recsys_json,
        language_options=available_languages(),
        frontend_plugin_suites=frontend_plugin_suites,
    )


def annotation_module_enabled(exp_id) -> bool:
    """Whether the "Post & Comment Annotation" add-on module is enabled for *exp_id*."""
    try:
        from y_web.src.models import FrontendAddsOnExpModuleSettings

        row = db.session.get(
            FrontendAddsOnExpModuleSettings, (exp_id, "post_annotation")
        )
        return bool(row is not None and row.enabled)
    except Exception:
        return False


def _clamped(value, setting):
    """``value`` inside the range its declaration gives (a bool never gets here)."""
    if setting is None:
        return value
    if setting.minimum is not None:
        value = max(type(value)(setting.minimum), value)
    if setting.maximum is not None:
        value = min(type(value)(setting.maximum), value)
    return value


# ------------------------------------------------------------------
# GET /admin/frontend_settings/get_settings?exp_id=N  — JSON API
# ------------------------------------------------------------------
@experiments.route("/admin/frontend_settings/get_settings", methods=["GET"])
@login_required
def frontend_settings_get():
    check_privileges(current_user.username)

    exp_id = request.args.get("exp_id", type=int)
    if not exp_id:
        return jsonify({"ok": False, "error": _("Missing exp_id")}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type not in supported_platforms():
        return jsonify({"ok": False, "error": _("Experiment not found")}), 404

    return jsonify(
        {
            "ok": True,
            "exp_id": exp_id,
            "exp_name": exp.exp_name,
            "platform_type": exp.platform_type,
            "capabilities": capabilities_for(exp.platform_type),
            "excluded_capabilities": excluded_capabilities_for(exp.platform_type),
            "simulator_type": exp.simulator_type or "Standard",
            "settings": _load_settings(exp_id),
            "annotation_module_enabled": annotation_module_enabled(exp_id),
            "recsys_options": _load_recsys_options(
                exp.simulator_type or "Standard", all_algorithms=True
            ),
            "platform_settings": _platform_setting_specs(exp.platform_type),
            **_frontend_wording(exp.platform_type),
        }
    )


# ------------------------------------------------------------------
# POST /admin/frontend_settings/save  — JSON API
# ------------------------------------------------------------------
@experiments.route("/admin/frontend_settings/save", methods=["POST"])
@login_required
def frontend_settings_save():
    check_privileges(current_user.username)

    data = request.get_json(silent=True) or {}
    exp_id = data.get("exp_id")
    new_settings = data.get("settings", {})

    if not exp_id:
        return jsonify({"ok": False, "error": _("Missing exp_id")}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type not in supported_platforms():
        return jsonify({"ok": False, "error": _("Experiment not found")}), 404

    declared = {
        setting.key: setting for setting in declared_settings(exp.platform_type)
    }
    table = defaults_for(exp.platform_type)
    safe = {}
    for k, default in table.items():
        if k not in new_settings:
            continue
        setting = declared.get(k)
        if isinstance(default, bool):
            safe[k] = bool(new_settings[k])
        elif isinstance(default, float):
            try:
                safe[k] = float(new_settings[k])
            except (TypeError, ValueError):
                safe[k] = default
            safe[k] = _clamped(safe[k], setting)
        elif isinstance(default, int):
            try:
                safe[k] = int(new_settings[k])
            except (TypeError, ValueError):
                safe[k] = default
            safe[k] = _clamped(safe[k], setting)
        else:
            # string settings (recsys names, sort mode...)
            value = str(new_settings[k])
            if k == "language":
                allowed = _language_choices()
            elif setting is not None and setting.choices:
                allowed = {item["name"] for item in setting.choices}
            else:
                allowed = None
            safe[k] = value if allowed is None or value in allowed else default
            if setting is not None and setting.strip:
                safe[k] = safe[k].strip()
            if setting is not None and setting.max_length:
                safe[k] = safe[k][: setting.max_length]

    if safe.get("show_annotation_stats") and not annotation_module_enabled(exp_id):
        safe["show_annotation_stats"] = (
            False  # nothing to show without the annotation add-on
        )

    row = db.session.get(ExpFrontendSettings, exp_id)
    if row is None:
        row = ExpFrontendSettings(exp_id=exp_id, settings_json=json.dumps(safe))
        db.session.add(row)
    else:
        # Merge with existing so unrelated sections are preserved
        try:
            existing = json.loads(row.settings_json or "{}")
        except Exception:
            existing = {}
        existing.update(safe)
        row.settings_json = json.dumps(existing)

    db.session.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Frontend plugin suites (group="frontend_plugins") — per-experiment module enable/config
# ------------------------------------------------------------------
def _frontend_plugin_module_status(manifest: dict, row) -> str:
    """Compute the admin-facing status label for one module manifest.

    One of: "incompatible" | "error" | "active" | "not_configured" |
    "disabled" | "available".
    """
    if not manifest.get("valid", True):
        errors = " ".join(manifest.get("errors") or [])
        if "app version" in errors:
            return "incompatible"
        return "error"

    enabled = bool(row is not None and row.enabled)
    if enabled:
        saved_cfg = {}
        if row is not None:
            try:
                saved_cfg = json.loads(row.config_json or "{}")
            except Exception:
                saved_cfg = {}
        merged = {p["name"]: p.get("default") for p in manifest.get("parameters", [])}
        merged.update(saved_cfg)
        for param in manifest.get("parameters", []):
            if param.get("required") and not merged.get(param["name"]):
                return "not_configured"
        return "active"

    return "disabled" if row is not None else "available"


def _frontend_plugin_module_config(manifest: dict, row) -> dict:
    merged = {p["name"]: p.get("default") for p in manifest.get("parameters", [])}
    if row is not None:
        try:
            merged.update(json.loads(row.config_json or "{}"))
        except Exception:
            pass
    return merged


def _manifest_for_platform(manifest: dict, platform: str):
    """Parameters and sections of *manifest* that apply to *platform*.

    A parameter or section may carry its own ``platforms`` list; one that
    does not applies everywhere the module itself does. Sections left with
    no parameter are dropped, so a platform never sees an empty heading.
    """

    def applies(item):
        scoped = item.get("platforms")
        return not scoped or platform in scoped

    params = [p for p in manifest.get("parameters") or [] if applies(p)]
    used = {p.get("section") for p in params}
    sections = [
        sec
        for sec in manifest.get("parameter_sections") or []
        if applies(sec) and sec.get("key") in used
    ]
    return sections, params


@experiments.route("/admin/frontend_settings/suite/<repo_key>/get", methods=["GET"])
@login_required
def frontend_plugin_suite_settings_get(repo_key):
    check_privileges(current_user.username)

    exp_id = request.args.get("exp_id", type=int)
    if not exp_id:
        return jsonify({"ok": False, "error": _("Missing exp_id")}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type not in supported_platforms():
        return jsonify({"ok": False, "error": _("Experiment not found")}), 404

    from y_web.src.external_runtime.frontend_plugins import (
        frontend_plugin_repo_keys,
        validate_frontend_suite,
    )
    from y_web.src.models import FrontendAddsOnExpModuleSettings

    if repo_key not in frontend_plugin_repo_keys():
        return jsonify({"ok": False, "error": _("Unknown suite")}), 404

    from y_web.src.external_runtime.registry import (
        runtime_installed_and_visible,
    )

    # Defense in depth: this suite may not even have been offered in the
    # /admin/frontend_settings listing above, but that listing filtering
    # it out must not be the ONLY thing stopping a direct call to this
    # endpoint from reaching a private, not-yet-visible suite.
    if not runtime_installed_and_visible(repo_key, current_user):
        return jsonify({"ok": False, "error": _("Unknown suite")}), 404

    report = validate_frontend_suite(repo_key)
    if not report["installed"]:
        return jsonify({"ok": True, "installed": False})

    rows = {
        row.module_id: row
        for row in db.session.query(FrontendAddsOnExpModuleSettings)
        .filter_by(exp_id=exp_id)
        .all()
    }

    from y_web.src.external_runtime.plugin_i18n import (
        localize_manifest,
        localize_text,
    )

    modules = []
    for manifest in report["modules"]:
        manifest = localize_manifest(repo_key, manifest)
        module_id = manifest.get("module_id")
        row = rows.get(module_id)
        shown_sections, shown_params = _manifest_for_platform(
            manifest, exp.platform_type
        )
        modules.append(
            {
                "module_id": module_id,
                "display_name": manifest.get("display_name") or module_id,
                "version": manifest.get("version"),
                "description": manifest.get("description") or "",
                "parameter_sections": shown_sections,
                "parameters": shown_params,
                "enabled": bool(row is not None and row.enabled),
                "config": _frontend_plugin_module_config(manifest, row),
                "status": _frontend_plugin_module_status(manifest, row),
                "manifest_errors": manifest.get("errors") or [],
                # Modules declare the platforms they work on; one that says
                # nothing is a default-platform-only module (its original scope).
                "platforms": manifest.get("platforms") or [registry.default_key()],
                "supported": exp.platform_type
                in (manifest.get("platforms") or [registry.default_key()]),
            }
        )

    return jsonify(
        {
            "ok": True,
            "installed": True,
            "valid": report["valid"],
            "platform_type": exp.platform_type,
            "suite": localize_manifest(repo_key, report.get("suite")),
            "suite_errors": report.get("errors") or [],
            "modules": modules,
        }
    )


def _coerce_frontend_plugin_param(value, param: dict):
    ptype = param.get("type")
    if ptype == "bool":
        return bool(value)
    if ptype == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return param.get("default", 0)
    if ptype == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return param.get("default", 0.0)
    if ptype == "enum":
        options = param.get("options") or []
        return value if value in options else param.get("default")
    if ptype == "string_list":
        if isinstance(value, list):
            return [str(v) for v in value]
        return param.get("default", [])
    return str(value) if value is not None else param.get("default", "")


@experiments.route("/admin/frontend_settings/suite/<repo_key>/save", methods=["POST"])
@login_required
def frontend_plugin_suite_settings_save(repo_key):
    check_privileges(current_user.username)

    data = request.get_json(silent=True) or {}
    exp_id = data.get("exp_id")
    module_id = data.get("module_id")
    enabled = bool(data.get("enabled"))
    raw_config = data.get("config") or {}

    if not exp_id or not module_id:
        return jsonify({"ok": False, "error": _("Missing exp_id or module_id")}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type not in supported_platforms():
        return jsonify({"ok": False, "error": _("Experiment not found")}), 404

    from y_web.src.external_runtime.frontend_plugins import (
        discover_frontend_modules,
        frontend_plugin_repo_keys,
    )
    from y_web.src.external_runtime.plugin_loader import ensure_module_schema
    from y_web.src.models import FrontendAddsOnExpModuleSettings

    if repo_key not in frontend_plugin_repo_keys():
        return jsonify({"ok": False, "error": _("Unknown suite")}), 404

    from y_web.src.external_runtime.registry import (
        runtime_installed_and_visible,
    )

    if not runtime_installed_and_visible(repo_key, current_user):
        return jsonify({"ok": False, "error": _("Unknown suite")}), 404

    manifest = None
    for entry in discover_frontend_modules(repo_key):
        if entry.get("module_id") == module_id:
            manifest = entry
            break
    if manifest is None:
        return jsonify({"ok": False, "error": _("Unknown module")}), 404
    if exp.platform_type not in (manifest.get("platforms") or [registry.default_key()]):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": _(
                        "This module is not available for this experiment type."
                    ),
                }
            ),
            409,
        )

    safe_config = {}
    _unused, applicable_params = _manifest_for_platform(manifest, exp.platform_type)
    for param in applicable_params:
        name = param["name"]
        if name in raw_config:
            safe_config[name] = _coerce_frontend_plugin_param(raw_config[name], param)

    if enabled:
        migrated = ensure_module_schema(repo_key, module_id, exp_id, quiet=True)
        if not migrated:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": _(
                            "Could not prepare the experiment database for this module."
                        ),
                    }
                ),
                500,
            )

    row = db.session.get(FrontendAddsOnExpModuleSettings, (exp_id, module_id))
    if row is None:
        row = FrontendAddsOnExpModuleSettings(
            exp_id=exp_id,
            module_id=module_id,
            enabled=enabled,
            config_json=json.dumps(safe_config),
        )
        db.session.add(row)
    else:
        existing_cfg = {}
        try:
            existing_cfg = json.loads(row.config_json or "{}")
        except Exception:
            pass
        existing_cfg.update(safe_config)
        row.enabled = enabled
        row.config_json = json.dumps(existing_cfg)

    db.session.commit()
    return jsonify({"ok": True})
