"""Whether the Agent Memory plugin is installed.

Agent memory comes from the ``Agent Memory`` plugin (``external/y_memory_subsystem``).
Every part of the experiment setup that is about memory is shown, and accepted by the
server, only while the plugin is checked out and holds the ``yclient_memory`` package.
"""

from __future__ import annotations

import os

from y_web.src.system.path_utils import get_writable_path

PLUGIN_FOLDER = "y_memory_subsystem"


def agent_memory_plugin_installed() -> bool:
    package = os.path.join(
        get_writable_path(), "external", PLUGIN_FOLDER, "src", "yclient_memory"
    )
    return os.path.isfile(os.path.join(package, "__init__.py"))
