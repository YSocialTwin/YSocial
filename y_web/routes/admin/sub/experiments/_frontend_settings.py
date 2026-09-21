"""
Frontend Settings admin route.

Allows administrators to configure UI parameters per experiment
(filtered to microblogging experiments).
Settings are stored in ExpFrontendSettings (one JSON row per experiment).
"""

import json

from flask import jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.src.models import ExpFrontendSettings, Exps
from y_web.src.models.config import Content_Recsys, Follow_Recsys
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments

# ------------------------------------------------------------------
# Default settings — all interactions shown/enabled
# ------------------------------------------------------------------
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
    # Feed & Profile
    "default_content_recsys": "",  # empty = system default
    "default_follow_recsys": "",  # empty = system default
    "profile_topics_box": True,  # show Topics & Opinions card in edit_profile
    "onboarding_enabled": True,  # show onboarding screen on first login
    # Infinite scroll & pagination
    "infinite_scroll_enabled": True,  # enable infinite scroll (False = paginate)
    "posts_per_page": 10,  # posts per page when infinite scroll is disabled
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


def _load_settings(exp_id: int) -> dict:
    row = db.session.get(ExpFrontendSettings, exp_id)
    if row is None:
        return dict(DEFAULT_SETTINGS)
    try:
        loaded = json.loads(row.settings_json or "{}")
    except Exception:
        loaded = {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(loaded)
    return merged


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
    (e.g. FilterBubble/Personalized Feed for human user profiles).
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
                        "label": r.value,
                        "category": r.category or "Other",
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

    micro_exps = db.session.scalars(
        select(Exps)
        .filter(Exps.platform_type == "microblogging")
        .order_by(Exps.exp_name.asc())
    ).all()

    exps_json = json.dumps(
        [
            {"id": e.idexp, "name": e.exp_name, "type": "microblogging"}
            for e in micro_exps
        ]
    )

    recsys = _load_recsys_options(all_algorithms=True)
    recsys_json = json.dumps(recsys)

    return render_template(
        "admin/frontend_settings.html",
        exps_json=exps_json,
        recsys_json=recsys_json,
    )


# ------------------------------------------------------------------
# GET /admin/frontend_settings/get_settings?exp_id=N  — JSON API
# ------------------------------------------------------------------
@experiments.route("/admin/frontend_settings/get_settings", methods=["GET"])
@login_required
def frontend_settings_get():
    check_privileges(current_user.username)

    exp_id = request.args.get("exp_id", type=int)
    if not exp_id:
        return jsonify({"ok": False, "error": "Missing exp_id"}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type != "microblogging":
        return jsonify({"ok": False, "error": "Experiment not found"}), 404

    return jsonify(
        {
            "ok": True,
            "exp_id": exp_id,
            "exp_name": exp.exp_name,
            "simulator_type": exp.simulator_type or "Standard",
            "settings": _load_settings(exp_id),
            "recsys_options": _load_recsys_options(
                exp.simulator_type or "Standard", all_algorithms=True
            ),
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
        return jsonify({"ok": False, "error": "Missing exp_id"}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type != "microblogging":
        return jsonify({"ok": False, "error": "Experiment not found"}), 404

    safe = {}
    for k, default in DEFAULT_SETTINGS.items():
        if k not in new_settings:
            continue
        if isinstance(default, bool):
            safe[k] = bool(new_settings[k])
        elif isinstance(default, float):
            try:
                safe[k] = float(new_settings[k])
            except (TypeError, ValueError):
                safe[k] = default
        elif isinstance(default, int):
            try:
                safe[k] = int(new_settings[k])
            except (TypeError, ValueError):
                safe[k] = default
        else:
            # string settings (recsys names, sort mode…)
            safe[k] = str(new_settings[k])

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
# Frontend Adds-on frontend plugin suite — per-experiment module enable/config
# ------------------------------------------------------------------
def _frontend_adds_on_module_status(manifest: dict, row) -> str:
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


def _frontend_adds_on_module_config(manifest: dict, row) -> dict:
    merged = {p["name"]: p.get("default") for p in manifest.get("parameters", [])}
    if row is not None:
        try:
            merged.update(json.loads(row.config_json or "{}"))
        except Exception:
            pass
    return merged


@experiments.route("/admin/frontend_settings/frontend_adds_on/get", methods=["GET"])
@login_required
def frontend_adds_on_settings_get():
    check_privileges(current_user.username)

    exp_id = request.args.get("exp_id", type=int)
    if not exp_id:
        return jsonify({"ok": False, "error": "Missing exp_id"}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type != "microblogging":
        return jsonify({"ok": False, "error": "Experiment not found"}), 404

    from y_web.src.external_runtime.frontend_plugins import validate_frontend_suite
    from y_web.src.models import FrontendAddsOnExpModuleSettings

    report = validate_frontend_suite("frontend_adds_on")
    if not report["installed"]:
        return jsonify({"ok": True, "installed": False})

    rows = {
        row.module_id: row
        for row in db.session.query(FrontendAddsOnExpModuleSettings)
        .filter_by(exp_id=exp_id)
        .all()
    }

    modules = []
    for manifest in report["modules"]:
        module_id = manifest.get("module_id")
        row = rows.get(module_id)
        modules.append(
            {
                "module_id": module_id,
                "display_name": manifest.get("display_name") or module_id,
                "version": manifest.get("version"),
                "description": manifest.get("description") or "",
                "parameter_sections": manifest.get("parameter_sections") or [],
                "parameters": manifest.get("parameters") or [],
                "enabled": bool(row is not None and row.enabled),
                "config": _frontend_adds_on_module_config(manifest, row),
                "status": _frontend_adds_on_module_status(manifest, row),
                "manifest_errors": manifest.get("errors") or [],
            }
        )

    return jsonify(
        {
            "ok": True,
            "installed": True,
            "valid": report["valid"],
            "suite": report.get("suite"),
            "suite_errors": report.get("errors") or [],
            "modules": modules,
        }
    )


def _coerce_frontend_adds_on_param(value, param: dict):
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


@experiments.route("/admin/frontend_settings/frontend_adds_on/save", methods=["POST"])
@login_required
def frontend_adds_on_settings_save():
    check_privileges(current_user.username)

    data = request.get_json(silent=True) or {}
    exp_id = data.get("exp_id")
    module_id = data.get("module_id")
    enabled = bool(data.get("enabled"))
    raw_config = data.get("config") or {}

    if not exp_id or not module_id:
        return jsonify({"ok": False, "error": "Missing exp_id or module_id"}), 400

    exp = db.session.get(Exps, exp_id)
    if exp is None or exp.platform_type != "microblogging":
        return jsonify({"ok": False, "error": "Experiment not found"}), 404

    from y_web.src.external_runtime.frontend_plugins import discover_frontend_modules
    from y_web.src.external_runtime.plugin_loader import ensure_module_schema
    from y_web.src.models import FrontendAddsOnExpModuleSettings

    manifest = None
    for entry in discover_frontend_modules("frontend_adds_on"):
        if entry.get("module_id") == module_id:
            manifest = entry
            break
    if manifest is None:
        return jsonify({"ok": False, "error": "Unknown module"}), 404

    safe_config = {}
    for param in manifest.get("parameters", []):
        name = param["name"]
        if name in raw_config:
            safe_config[name] = _coerce_frontend_adds_on_param(raw_config[name], param)

    if enabled:
        migrated = ensure_module_schema(
            "frontend_adds_on", module_id, exp_id, quiet=True
        )
        if not migrated:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Could not prepare the experiment database for this module.",
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
