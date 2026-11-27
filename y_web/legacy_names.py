"""Names the core used before the platform API 1.6 and still honours, for software that did not move yet.

* the ``StandardRuntime`` entry script and modules of the first engines, applied (with a ``DeprecationWarning``) to a
  provider that does not declare its runtime;
* the environment flags that once marked a spawned simulation process (``Y_SOCIAL_SUBPROCESS`` replaces them).

This module is the only place of the core that holds them, it is listed in
``scripts/metrics/decoupling_allowlist.json`` and goes away with the platform API 2.0.
"""

SERVER_SCRIPT = "y_server_run.py"
SERVER_APP_MODULE = "y_server"
CLIENT_CLASS_PATH = "y_client.clients:YClientWeb"

SUBPROCESS_FLAGS = ("Y_CLIENT_SUBPROCESS", "Y_SERVER_SUBPROCESS")
