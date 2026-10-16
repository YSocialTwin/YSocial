"""Extract translatable strings from plugin manifests (``meta/*.json``)."""

import json
from pathlib import Path

# Manifest keys whose string values are shown to users.
MANIFEST_KEYS = {
    "name",
    "display_name",
    "description",
    "label",
    "title",
    "help",
    "placeholder",
    "tooltip",
    "category",
    "group",
    "summary",
}


def _walk(obj, path, out):
    if isinstance(obj, dict):
        # A parameter definition ({"name": "max_items", "type": ...}) names an
        # identifier, not user-visible text: its ``label`` is the text to translate.
        is_parameter = "name" in obj and ("type" in obj or "section" in obj)
        for key, value in obj.items():
            if isinstance(value, str):
                if key == "name" and is_parameter:
                    continue
                if key in MANIFEST_KEYS and any(ch.isalpha() for ch in value):
                    out.append((value.strip(), f"{path}/{key}"))
            else:
                _walk(value, f"{path}/{key}", out)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _walk(value, f"{path}[{index}]", out)


def extract_plugin_manifests(plugin_dir):
    """Return ``[(text, "meta/file.json/path"), ...]`` for every manifest string."""
    plugin_dir = Path(plugin_dir)
    out = []
    for manifest in sorted((plugin_dir / "meta").glob("*.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        _walk(data, f"meta/{manifest.name}", out)
    return out
