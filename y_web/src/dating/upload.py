"""Import of an uploaded dating experiment: validated, never given the YSocial schema.

Inputs only (a database or lock from another installation is dropped). The client files are checked one by one;
clients and populations are created again from the admin pages.
"""

import json
import os
import shutil

from flask import current_app, flash, redirect, request, url_for

from y_web.i18n import gettext as _
from y_web.sdk import services
from y_web.src.dating import DATING_PLATFORM
from y_web.src.dating.clone import clear_dating_run_artifacts, rewrite_server_config
from y_web.src.dating.validation import DatingValidationError, validate_dating_folder


def import_uploaded_experiment(exp_dir, uid, exp_name_override, exp_group):
    """Register the dating experiment unpacked in ``exp_dir``; returns the redirect to show."""

    def refuse(message):
        shutil.rmtree(exp_dir, ignore_errors=True)
        flash(message)
        return redirect(request.referrer or url_for("admin.dashboard"))

    if services.database_type() == "postgresql":
        return refuse(_("Dating experiments are not supported with PostgreSQL."))
    try:
        with open(
            os.path.join(exp_dir, "server_config.json"), "r", encoding="utf-8"
        ) as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        return refuse(
            _("The uploaded dating experiment has no readable server configuration.")
        )

    name = exp_name_override or str(config.get("experiment_name") or "").strip()
    if not name:
        return refuse(_("The uploaded experiment has no name. Please provide one."))
    if services.experiment_name_taken(name):
        return refuse(
            _(
                "The experiment already exists. Please check the experiment name and try again."
            )
        )
    suggested_port = services.suggested_port()
    if not suggested_port:
        return refuse(
            _(
                "Error: No available port found in range 5000-6000. Cannot upload experiment."
            )
        )

    clear_dating_run_artifacts(exp_dir)
    try:
        validate_dating_folder(exp_dir)
        for item in sorted(os.listdir(exp_dir)):
            if item.startswith("client_") and item.endswith(".json"):
                validate_dating_folder(exp_dir, client_config=item)
    except DatingValidationError as exc:
        return refuse(
            _(
                "The uploaded dating experiment is not valid: %(errors)s",
                errors="; ".join(exc.messages),
            )
        )
    except (
        Exception
    ) as exc:  # validator unavailable: do not register what cannot be checked
        current_app.logger.warning(
            "dating validator could not run for an upload: %s", exc
        )
        return refuse(_("The uploaded dating experiment could not be validated."))

    folder = os.path.join(services.writable_path(), "y_web", "experiments", uid)
    rewrite_server_config(
        exp_dir, name, os.path.join(folder, "database_server.db"), folder + os.sep
    )
    services.register_uploaded_hpc_experiment(
        name=name,
        uid=uid,
        platform_type=DATING_PLATFORM,
        exp_group=exp_group,
        port=suggested_port,
    )
    flash(
        _(
            "Dating experiment imported. Create its populations and clients from the experiment page."
        )
    )
    return redirect(request.referrer or url_for("admin.dashboard"))
