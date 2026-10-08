

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
        modules.append({
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
        })

    return jsonify({
        "ok": True,
        "installed": True,
        "valid": report["valid"],
        "suite": report.get("suite"),
        "suite_errors": report.get("errors") or [],
        "modules": modules,
    })


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
        migrated = ensure_module_schema("frontend_adds_on", module_id, exp_id, quiet=True)
        if not migrated:
            return jsonify({
                "ok": False,
                "error": "Could not prepare the experiment database for this module.",
            }), 500

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
