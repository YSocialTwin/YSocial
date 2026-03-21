"""
Admin sub-blueprint package.

Each file here is the canonical source for one administrative Blueprint.
"""

from .agents import agents
from .clients import clientsr
from .experiments import experiments
from .jupyterlab import lab
from .ollama import ollama
from .pages import pages
from .populations import population
from .tutorial import tutorial
from .users import users

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
