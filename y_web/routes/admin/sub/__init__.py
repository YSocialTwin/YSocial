"""
Admin sub-blueprint package.

Each file here is the canonical source for one administrative Blueprint.
"""

from . import experiments as experiments_pkg
from .agents import agents
from .clients import clientsr
from .jupyterlab import lab
from .ollama import ollama
from .pages import pages
from .populations import population
from .tutorial import tutorial
from .users import users

experiments = experiments_pkg.experiments
# Preserve dotted patch/import paths like
# ``y_web.routes.admin.sub.experiments._schedule`` even though this package
# also re-exports the Blueprint as ``experiments``.
experiments._schedule = experiments_pkg._schedule
experiments._helpers = experiments_pkg._helpers

__all__ = [
    "agents",
    "clientsr",
    "experiments",
    "lab",
    "ollama",
    "pages",
    "population",
    "tutorial",
    "users",
]
