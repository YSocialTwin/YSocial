# runtime_hook_metadata_patch.py
import importlib.metadata
import sys

# List all packages that will be queried at runtime
KNOWN_PACKAGES = [
    "anyio",
    "autogen",
    "autogen-agentchat",
    "autogen-core",
    "autogen-ext",
    "pyautogen",
    "pyautogen-agentchat",
    "annotated_types",
    "fast_depends",
    "pydantic",
    "pydantic_core",
]

_orig_version = importlib.metadata.version


def patched_version(pkg_name):
    if pkg_name in KNOWN_PACKAGES:
        return "0.0.0"  # dummy version to prevent StopIteration
    return _orig_version(pkg_name)


importlib.metadata.version = patched_version
