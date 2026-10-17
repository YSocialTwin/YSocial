"""Language packs of the LLM prompts shipped in ``data_schema/prompts/<language>/``.

English is the source: every other language is a folder with the same file names and a ``manifest.json``.
A pack may translate only part of the keys; whatever is missing is taken from English (with a warning), so a
half-finished language still works. Nothing is translated at run time and users' custom prompts are never
touched: a pack is only used to write the prompt file an experiment or client starts from.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List

from y_web.src.system.path_utils import get_resource_path

DEFAULT_LANGUAGE = "en"
PACK_FILES = ("prompts.json", "prompts_forum.json", "prompts_hpc.json", "prompts_ygram.json")
_LANG = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
log = logging.getLogger(__name__)


def packs_root() -> Path:
    return Path(get_resource_path(os.path.join("data_schema", "prompts")))


def normalize(language) -> str:
    """A safe language code; anything empty, malformed or without a pack means English."""
    code = (language or "").strip().lower()
    if code and _LANG.match(code) and (packs_root() / code / "manifest.json").exists():
        return code
    return DEFAULT_LANGUAGE


def manifest(language: str) -> Dict:
    with open(packs_root() / normalize(language) / "manifest.json", encoding="utf-8") as handle:
        return json.load(handle)


def languages() -> List[Dict]:
    """The available packs as ``{"code", "name", "native_name"}``, English first."""
    found = []
    for folder in sorted(p for p in packs_root().iterdir() if (p / "manifest.json").exists()):
        data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        found.append(
            {
                "code": folder.name,
                "name": data.get("name", folder.name),
                "native_name": data.get("native_name", data.get("name", folder.name)),
            }
        )
    found.sort(key=lambda item: (item["code"] != DEFAULT_LANGUAGE, item["code"]))
    return found


def _merge(base, over, language, where, missing):
    """``base`` with the entries of ``over`` laid on top, key by key, at any depth."""
    if not isinstance(base, dict):
        return copy.deepcopy(over if over is not None else base)
    merged = copy.deepcopy(base)
    for key, value in base.items():
        path = f"{where}/{key}"
        if not isinstance(over, dict) or key not in over:
            missing.append(path)
        elif isinstance(value, dict):
            merged[key] = _merge(value, over[key], language, path, missing)
        else:
            merged[key] = over[key]
    return merged


def load_pack(name: str, language=None) -> Dict:
    """The prompts of file ``name`` in ``language``, with English filling the keys it lacks."""
    code = normalize(language)
    with open(packs_root() / DEFAULT_LANGUAGE / name, encoding="utf-8") as handle:
        english = json.load(handle)
    if code == DEFAULT_LANGUAGE:
        return english
    path = packs_root() / code / name
    if not path.exists():
        log.warning("prompt file %s has no %r version; using English", name, code)
        return english
    with open(path, encoding="utf-8") as handle:
        translated = json.load(handle)
    missing: List[str] = []
    merged = _merge(english, translated, code, name, missing)
    if missing:
        log.warning("%s (%s): %d prompt keys fall back to English", name, code, len(missing))
    return merged


def write_pack(name: str, destination, language=None) -> None:
    """Write the prompt file an experiment or client starts from.

    English is copied byte for byte; other languages are written as the merged JSON.
    """
    code = normalize(language)
    destination = Path(destination)
    source = packs_root() / code / name
    if code == DEFAULT_LANGUAGE or not source.exists():
        shutil.copyfile(packs_root() / DEFAULT_LANGUAGE / name, destination)
        return
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(load_pack(name, code), handle, ensure_ascii=False, indent=4)


def resolve(requested, default=None) -> str:
    """The language to use: the requested one if it has a pack, else the default, else English."""
    code = (requested or "").strip().lower()
    if code and normalize(code) == code:
        return code
    return normalize(default)
