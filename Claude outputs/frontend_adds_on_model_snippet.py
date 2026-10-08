

class FrontendAddsOnExpModuleSettings(db.Model):
    """Per-experiment, per-module configuration for the Frontend Adds-on plugin suite.

    One row per (exp_id, module_id) pair — e.g. (12, "post_annotation").
    ``enabled`` gates whether the module's blueprint routes accept requests
    for that experiment and whether its frontend assets are injected into
    that experiment's feed/thread pages (see
    ``y_web.src.external_runtime.plugin_loader.active_modules_context``).
    ``config_json`` holds only the parameters the admin explicitly saved;
    it is merged over the module manifest's own defaults at read time, so
    adding a new parameter to a module later never requires a data migration
    here.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "frontend_adds_on_exp_module_settings"

    exp_id = db.Column(
        db.Integer,
        db.ForeignKey("exps.idexp"),
        primary_key=True,
        nullable=False,
    )
    module_id = db.Column(db.String(100), primary_key=True, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    config_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now(),
    )
