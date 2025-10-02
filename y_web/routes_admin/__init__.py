"""
Administrative route modules.

Contains Flask blueprints for various administrative functions including
Ollama model management, population configuration, page management, agent
configuration, user management, experiment setup, and client configuration.
"""

from .agents_routes import *
from .clients_routes import *
from .experiments_routes import *
from .ollama_routes import *
from .pages_routes import *
from .populations_routes import *
from .users_routes import *
