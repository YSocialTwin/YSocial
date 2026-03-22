"""Client admin routes sub-package."""
from . import _agents, _crud, _details, _execution, _opinion, _recsys
from ._blueprint import clientsr
from ._crud import (
    create_client,
    create_forum_client,
    create_hpc_client,
    create_standard_client,
    delete_client,
)

__all__ = [
    "clientsr",
    "create_client",
    "create_forum_client",
    "create_hpc_client",
    "create_standard_client",
    "delete_client",
]
