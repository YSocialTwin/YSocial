"""Folders of the application."""

from y_web.sdk.runtime import get_writable_path

from ._forward import forward

get_base_path = forward(
    "y_web.src.system.path_utils",
    "get_base_path",
    name="get_base_path",
    doc="Folder of the installation (where the application code lives); same arguments as the core function.",
)

__all__ = ["get_base_path", "get_writable_path"]
