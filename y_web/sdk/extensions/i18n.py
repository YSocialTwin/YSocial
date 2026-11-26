"""Translation of the texts of a plugin, from the catalog of the plugin itself."""

from ._forward import forward

plugin_gettext = forward(
    "y_web.src.external_runtime.plugin_i18n",
    "plugin_gettext",
    name="plugin_gettext",
    doc="Translate ``message`` with the catalog ``domain`` of a plugin; same arguments as the core function.",
)
plugin_ngettext = forward(
    "y_web.src.external_runtime.plugin_i18n",
    "plugin_ngettext",
    name="plugin_ngettext",
    doc="Plural form of :func:`plugin_gettext`; same arguments as the core function.",
)

__all__ = ["plugin_gettext", "plugin_ngettext"]
