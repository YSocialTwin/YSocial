import pytest
pytestmark = pytest.mark.skip

import importlib.util
import sys
import types
from pathlib import Path


def _load_module(module_path, module_name):
    fake_y_server = types.ModuleType("y_server")
    fake_modals = types.ModuleType("y_server.modals")

    class FakePostToxicity:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_modals.Post_Toxicity = FakePostToxicity
    fake_y_server.modals = fake_modals

    sys.modules["y_server"] = fake_y_server
    sys.modules["y_server.modals"] = fake_modals

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


class _FakeDb:
    def __init__(self):
        self.session = _FakeSession()


def _install_fake_detoxify(prediction):
    fake_module = types.ModuleType("detoxify")

    class FakeDetoxify:
        def __init__(self, _model_name):
            pass

        def predict(self, _text):
            return prediction

    fake_module.Detoxify = FakeDetoxify
    sys.modules["detoxify"] = fake_module


def test_yserver_uses_detoxify_when_toxicity_active_without_api_key():
    module = _load_module(
        Path(
            "external/YServer/y_server/content_analysis/textual_data.py"
        ),
        "yserver_textual_data_test",
    )
    _install_fake_detoxify(
        {
            "toxicity": 0.6,
            "severe_toxicity": 0.3,
            "identity_attack": 0.2,
            "insult": 0.4,
            "obscene": 0.5,
            "threat": 0.1,
            "sexual_explicit": 0.05,
        }
    )

    db = _FakeDb()
    module.toxicity("sample text", None, 17, db)

    assert db.session.committed is True
    assert len(db.session.added) == 1
    saved = db.session.added[0]
    assert saved.post_id == 17
    assert saved.toxicity == 0.6
    assert saved.profanity == 0.5
    assert saved.sexually_explicit == 0.05
    assert saved.flirtation == 0.0


def test_yserver_reddit_uses_detoxify_when_toxicity_active_without_api_key():
    module = _load_module(
        Path(
            "external/YServerReddit/y_server/content_analysis/textual_data.py"
        ),
        "yserver_reddit_textual_data_test",
    )
    _install_fake_detoxify(
        {
            "toxicity": [0.7],
            "severe_toxicity": [0.2],
            "identity_attack": [0.1],
            "insult": [0.35],
            "obscene": [0.45],
            "threat": [0.05],
            "sexual_explicit": [0.15],
        }
    )

    db = _FakeDb()
    module.toxicity("sample text", "", 21, db)

    assert db.session.committed is True
    assert len(db.session.added) == 1
    saved = db.session.added[0]
    assert saved.post_id == 21
    assert saved.toxicity == 0.7
    assert saved.profanity == 0.45
    assert saved.sexually_explicit == 0.15
    assert saved.flirtation == 0.0
