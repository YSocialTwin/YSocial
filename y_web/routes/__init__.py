"""
Central blueprint registry.

Call ``register_blueprints(app)`` from ``y_web/__init__.py`` instead of the
current manual import-and-register block.

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


def register_blueprints(app):
    """Register all application blueprints with *app*."""
    from .social import main
    from .interactions import user
    from .auth import auth
    from .errors import errors
    from .admin import admin
    from .admin.sub import (
        agents, clientsr, experiments, lab,
        ollama, pages, population, tutorial, users,
    )
    from .api import api_reddit, api_interview

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(user)
    app.register_blueprint(admin)
    app.register_blueprint(ollama)
    app.register_blueprint(population)
    app.register_blueprint(pages)
    app.register_blueprint(agents)
    app.register_blueprint(users)
    app.register_blueprint(experiments)
    app.register_blueprint(clientsr)
    app.register_blueprint(errors)
    app.register_blueprint(lab)
    app.register_blueprint(tutorial)
    app.register_blueprint(api_reddit)
    app.register_blueprint(api_interview)
