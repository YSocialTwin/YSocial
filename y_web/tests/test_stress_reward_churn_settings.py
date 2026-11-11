"""The churn curve of stress/reward is editable from the Stress / Reward settings page."""

import json

from y_web.tests.test_im_admin_pages import _make_im_experiment, im_app  # noqa: F401


def _folder(app, tmp_path, exp_id, switch=True):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        uid = db.session.get(Exps, exp_id).db_name.split("/")[1]
    folder = tmp_path / "y_web" / "experiments" / uid
    folder.mkdir(parents=True)
    (folder / "server_config.json").write_text(
        json.dumps(
            {"stress_reward_enabled": switch, "stress_reward": {"enabled": switch}}
        )
    )
    return folder


def _churn(folder):
    return json.loads((folder / "server_config.json").read_text())["stress_reward"][
        "system"
    ]["churn"]


def test_the_page_shows_the_churn_curve_with_the_defaults(im_app, tmp_path):
    app, client = im_app
    exp_id = _make_im_experiment(app)
    _folder(app, tmp_path, exp_id)
    page = client.get(f"/admin/stress_reward_settings/{exp_id}").data.decode()
    for name, value in [
        ("sr_churn_stress_weight", "2.0"),
        ("sr_churn_reward_weight", "1.0"),
        ("sr_churn_bias", "-1.8"),
        ("sr_churn_temperature", "0.3"),
        ("sr_churn_min_probability", "0.0"),
        ("sr_churn_max_probability", "0.95"),
    ]:
        assert f'name="{name}"' in page and f'value="{value}"' in page, name


def test_the_churn_curve_is_saved_and_churn_stays_off_unless_switched_on(
    im_app, tmp_path
):
    app, client = im_app
    exp_id = _make_im_experiment(app)
    folder = _folder(app, tmp_path, exp_id)
    response = client.post(
        f"/admin/update_stress_reward_settings/{exp_id}",
        data={
            "sr_churn_stress_weight": "2.5",
            "sr_churn_reward_weight": "1.2",
            "sr_churn_bias": "-1.5",
            "sr_churn_temperature": "0.25",
            "sr_churn_min_probability": "0.01",
            "sr_churn_max_probability": "0.8",
        },
    )
    assert response.status_code in (200, 302)
    churn = _churn(folder)
    assert churn["enabled"] is False  # the switch was not sent: churn must be explicit
    assert (churn["stress_weight"], churn["reward_weight"], churn["bias"]) == (
        2.5,
        1.2,
        -1.5,
    )
    assert (churn["temperature"], churn["min_probability"], churn["max_probability"]) == (
        0.25,
        0.01,
        0.8,
    )
    client.post(
        f"/admin/update_stress_reward_settings/{exp_id}",
        data={"sr_churn_enabled": "on"},
    )
    churn = _churn(folder)  # fields that are not sent keep what was saved
    assert churn["enabled"] is True and churn["bias"] == -1.5


def test_invalid_churn_values_are_clamped(im_app, tmp_path):
    app, client = im_app
    exp_id = _make_im_experiment(app)
    folder = _folder(app, tmp_path, exp_id)
    client.post(
        f"/admin/update_stress_reward_settings/{exp_id}",
        data={
            "sr_churn_stress_weight": "-3",
            "sr_churn_temperature": "0",
            "sr_churn_min_probability": "0.9",
            "sr_churn_max_probability": "0.2",
            "sr_churn_bias": "not a number",
        },
    )
    churn = _churn(folder)
    assert churn["stress_weight"] == 0.0 and churn["temperature"] == 0.01
    assert (churn["min_probability"], churn["max_probability"]) == (0.2, 0.9)
    assert churn["bias"] == -1.8  # unreadable value: the previous one stays
