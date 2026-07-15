"""
Regression tests for optional YSimulator text-support dependencies.
"""

import builtins
import importlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")
EXTERNAL_YSIMULATOR = ROOT / "external" / "YSimulator"
if str(EXTERNAL_YSIMULATOR) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_YSIMULATOR))


def test_annotations_module_imports_without_detoxify_or_perspective(monkeypatch):
    """
    YSimulator text-support modules must not require Detoxify/Torch at import time.

    The HPC client imports text annotation helpers even when toxicity scoring is
    disabled, so the module has to stay importable on machines that do not have
    the Detoxify/Torch stack available.
    """

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"detoxify", "perspective"}:
            raise AssertionError(f"unexpected eager import of {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "YSimulator.YClient.text_support.annotations", raising=False)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module("YSimulator.YClient.text_support.annotations")

    assert hasattr(module, "toxicity")
    assert hasattr(module, "vader_sentiment")


def test_annotations_toxicity_handles_missing_detoxify(monkeypatch):
    """
    Local toxicity scoring should fail closed when Detoxify is unavailable.
    """

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "detoxify":
            raise ImportError("detoxify not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    module = importlib.import_module("YSimulator.YClient.text_support.annotations")
    module = importlib.reload(module)

    assert module.toxicity("hello world", None) == {}
