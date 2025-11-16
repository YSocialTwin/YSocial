# runtime_hook_splash_fix.py
# Ensure _PYI_SPLASH_IPC environment variable exists to avoid splash KeyError

import os

if "_PYI_SPLASH_IPC" not in os.environ:
    os.environ["_PYI_SPLASH_IPC"] = ""
