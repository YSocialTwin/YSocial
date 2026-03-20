"""
Administrative route modules.

Each name is imported directly so that importing one module does not
force the import of all others.
"""

try:
    from .agents_routes import agents
except ImportError:
    agents = None  # type: ignore[assignment]

try:
    from .clients_routes import clientsr
except ImportError:
    clientsr = None  # type: ignore[assignment]

try:
    from .experiments_routes import experiments
except ImportError:
    experiments = None  # type: ignore[assignment]

try:
    from .jupyterlab_routes import lab
except ImportError:
    lab = None  # type: ignore[assignment]

try:
    from .ollama_routes import ollama
except ImportError:
    ollama = None  # type: ignore[assignment]

try:
    from .pages_routes import pages
except ImportError:
    pages = None  # type: ignore[assignment]

try:
    from .populations_routes import population
except ImportError:
    population = None  # type: ignore[assignment]

try:
    from .tutorial_routes import tutorial
except ImportError:
    tutorial = None  # type: ignore[assignment]

try:
    from .users_routes import users
except ImportError:
    users = None  # type: ignore[assignment]

__all__ = [
    "agents", "clientsr", "experiments", "lab",
    "ollama", "pages", "population", "tutorial", "users",
]
