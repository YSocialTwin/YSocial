#!/usr/bin/env python
"""Smoke checks of a freshly installed YSocial (run by ``fresh_install_check.sh``, inside the new checkout).

It builds the application on an empty data folder, signs in as the default administrator, opens the pages that the
platforms and extensions add, and creates one experiment for every platform and runtime that is installed. The first
failing step stops the run (exit status 1); every step, passed or not, is written to the report.

    YSOCIAL_HOME=<checkout> python scripts/dev/fresh_install_check.py <report.json>

The data folder is the checkout, so run it on a throw-away clone only.
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "external")]

PASSWORD = "fresh-install-check"
ADMIN_PAGES = [
    "/admin/dashboard",
    "/admin/experiments",
    "/admin/frontend_settings",
    "/admin/scenario_design/app",
    "/admin/plugins",
]

REPORT = []


def step(name):
    """Decorator: run a step, record it, stop the whole run on the first failure."""

    def wrap(fn):
        started = time.time()
        try:
            detail = fn()
            REPORT.append({"step": name, "ok": True, "detail": detail, "seconds": round(time.time() - started, 2)})
            print(f"  ok   {name}" + (f" ({detail})" if detail else ""))
        except Exception as exc:  # noqa: BLE001 - the report must name any failure
            REPORT.append(
                {"step": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}
            )
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            finish(1)
        return fn

    return wrap


def finish(code):
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fresh_install_report.json"
    target.write_text(json.dumps(REPORT, indent=1, ensure_ascii=False), encoding="utf-8")
    sys.exit(code)


def main():
    os.environ.setdefault("YSOCIAL_HOME", str(ROOT))
    state = {}

    @step("the application starts on an empty data folder")
    def _start():
        from y_web import create_app, db
        from y_web.sdk.models import Admin_users
        from werkzeug.security import generate_password_hash

        app = create_app(db_type="sqlite")
        with app.app_context():
            admin = db.session.query(Admin_users).first()
            assert admin is not None, "no default administrator was created"
            state["email"] = admin.email
            admin.password = generate_password_hash(PASSWORD)
            db.session.commit()
        state["app"] = app
        state["client"] = app.test_client()
        return "default administrator found"

    @step("the administrator signs in")
    def _login():
        reply = state["client"].post("/login", data={"email": state["email"], "password": PASSWORD})
        assert reply.status_code == 302 and "/admin" in (reply.headers.get("Location") or ""), reply.status_code

    for page in ADMIN_PAGES:

        @step(f"{page} opens")
        def _page(page=page):
            reply = state["client"].get(page, follow_redirects=True)
            assert reply.status_code == 200, f"HTTP {reply.status_code}"
            assert b"Traceback" not in reply.data, "the page shows a traceback"

    @step("every installed platform is registered")
    def _platforms():
        from y_web.platforms import registry

        found = [(p.key, p.provider_id, tuple(p.simulator_types or ())) for p in registry.all_providers()]
        assert found, "no platform provider is registered"
        state["platforms"] = found
        return ", ".join(sorted({f"{key}/{pid}" for key, pid, _ in found}))

    @step("an experiment is created for every platform and runtime")
    def _experiments():
        from y_web import db
        from y_web.sdk.models import Exps
        from sqlalchemy import select

        made = []
        for key, provider_id, runtimes in state["platforms"]:
            for runtime in runtimes or ("Standard",):
                name = f"fresh_{provider_id}_{runtime}".replace("-", "_")
                reply = state["client"].post(
                    "/admin/create_experiment",
                    data={
                        "exp_name": name,
                        "exp_descr": "fresh install check",
                        "platform_type": key,
                        "simulator_type": runtime,
                        "tags": "check",
                    },
                    follow_redirects=False,
                )
                assert reply.status_code in (200, 302), f"{name}: HTTP {reply.status_code}"
                with state["app"].app_context():
                    row = db.session.scalars(select(Exps).filter_by(exp_name=name)).first()
                    assert row is not None, f"{name}: no experiment was stored"
                    made.append((row.idexp, key, row.simulator_type))
        state["experiments"] = made
        return f"{len(made)} experiments"

    @step("the details page of every experiment opens")
    def _details():
        for exp_id, key, runtime in state["experiments"]:
            reply = state["client"].get(f"/admin/experiment_details/{exp_id}", follow_redirects=True)
            assert reply.status_code == 200, f"experiment {exp_id} ({key}/{runtime}): HTTP {reply.status_code}"
            assert b"Traceback" not in reply.data, f"experiment {exp_id}: traceback in the page"

    finish(0)


if __name__ == "__main__":
    main()
