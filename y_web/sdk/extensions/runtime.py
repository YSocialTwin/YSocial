"""The plugin runtime: discovery, schemas, switches."""

from ._forward import forward


def registered_suite_keys() -> list:
    """Keys of the plugin suites registered so far."""
    from y_web.src.external_runtime import plugin_loader

    return list(getattr(plugin_loader, "_REGISTERED_SUITES", {}))


ensure_module_schema = forward(
    "y_web.src.external_runtime.plugin_loader",
    "ensure_module_schema",
    name="ensure_module_schema",
    doc="Create or upgrade the tables of a plugin module; same arguments as the core function.",
)
discover_frontend_modules = forward(
    "y_web.src.external_runtime.frontend_plugins",
    "discover_frontend_modules",
    name="discover_frontend_modules",
    doc="The frontend modules found on disk; same arguments as the core function.",
)
plugin_enabled = forward(
    "y_web.src.external_runtime.backend_plugins",
    "plugin_enabled",
    name="plugin_enabled",
    doc="Whether a backend plugin is switched on; same arguments as the core function.",
)
training_component_catalog = forward(
    "y_web.src.external_runtime.backend_plugins",
    "training_component_catalog",
    name="training_component_catalog",
    doc="The components a training plugin may offer; same arguments as the core function.",
)
registered_suite_modules = forward(
    "y_web.src.external_runtime.plugin_loader",
    "registered_suite_modules",
    name="registered_suite_modules",
    doc="The modules a registered suite offers; same arguments as the core function.",
)
runtime_spec = forward(
    "y_web.src.external_runtime.registry",
    "runtime_spec",
    name="runtime_spec",
    doc="The runtime description of an external repository; same arguments as the core function.",
)

__all__ = [
    "discover_frontend_modules",
    "ensure_module_schema",
    "plugin_enabled",
    "registered_suite_keys",
    "registered_suite_modules",
    "runtime_spec",
    "training_component_catalog",
]
