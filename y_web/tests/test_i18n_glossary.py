"""The Italian catalogs must follow the approved glossary (docs/i18n/glossary.csv)."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "i18n" / "check_glossary.py"


def test_italian_catalogs_follow_glossary():
    spec = importlib.util.spec_from_file_location("check_glossary", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check() == []
