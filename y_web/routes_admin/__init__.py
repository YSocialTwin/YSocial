"""Backward-compatibility shim — source files have moved to routes/admin/sub/."""
from y_web.routes.admin.sub import (  # noqa: F401
    agents, clientsr, experiments, lab,
    ollama, pages, population, tutorial, users,
)
