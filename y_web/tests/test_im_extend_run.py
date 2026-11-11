import json

from y_web.routes.admin.sub.clients import _execution, _im
from y_web.src.im.experiment_config import apply_time_parameters, load_server_config


class _Exp:
    pass


def test_extension_grows_the_server_run_length(tmp_path, monkeypatch):
    (tmp_path / "server_config.json").write_text(
        json.dumps({"simulation": {"num_days": 1}})
    )
    monkeypatch.setattr(_im, "_experiment_folder", lambda exp: str(tmp_path))
    _execution._extend_im_server_run(_Exp(), 11)
    assert load_server_config(str(tmp_path))["simulation"]["num_days"] == 11
    _execution._extend_im_server_run(_Exp(), 5)  # never shortens
    assert load_server_config(str(tmp_path))["simulation"]["num_days"] == 11


def test_started_run_can_grow_but_not_change_start_date_or_round_length():
    cfg = {
        "simulation": {"num_days": 1, "start_date": "2026-10-30"},
        "telegram": {"time": {"ticks_per_round": 12}},
    }
    apply_time_parameters(cfg, days=5, run_started=True)
    assert cfg["simulation"]["num_days"] == 5
    for kwargs in ({"start_date": "2026-11-01"}, {"ticks_per_round": 6}):
        try:
            apply_time_parameters(cfg, run_started=True, **kwargs)
        except Exception as exc:
            assert "already started" in str(exc)
        else:
            raise AssertionError("must be refused")
