"""
Central route registry for the YSocial web application.

This package collects all Flask blueprints and exposes a single
``register_blueprints(app)`` factory that ``y_web/__init__.py`` calls
during application start-up.

Sub-packages
------------
social/         Blueprint "main"         – microblogging + forum views
interactions/   Blueprint "user_actions" – follow, publish, react, …
auth/           Blueprint "auth"         – login / logout / experiment select
errors/         Blueprint "errors"       – 400 / 403 / 404 / 500 handlers
admin/          Blueprint "admin"        – admin dashboard
admin/sub/      (re-exports routes_admin blueprints)
api/            Blueprints "api_reddit", "api_interview"
"""
