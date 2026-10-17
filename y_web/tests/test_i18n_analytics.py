"""Analytics pages: chart titles, descriptions and labels follow the admin language."""
import sqlite3

from flask import Flask

import y_web.i18n as i18n
from y_web.routes.admin.sub.experiments._opinion import _build_network_analytics_payload


def _db(tmp_path):
    path = tmp_path / "n.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """CREATE TABLE user_mgmt (id TEXT PRIMARY KEY, username TEXT NOT NULL);
            CREATE TABLE rounds (id TEXT PRIMARY KEY, day INTEGER NOT NULL, hour INTEGER NOT NULL);
            CREATE TABLE follow (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, follower_id TEXT NOT NULL, action TEXT, round TEXT);"""
        )
        conn.executemany("INSERT INTO user_mgmt VALUES (?,?)", [("u1", "a"), ("u2", "b")])
        conn.executemany("INSERT INTO rounds VALUES (?,?,?)", [("r1", 1, 1), ("r2", 2, 1)])
        conn.execute("INSERT INTO follow VALUES ('f1','u2','u1','follow','r1')")
        conn.commit()
    return str(path)


def test_network_analysis_payload_is_translated(tmp_path):
    app = Flask("y_web")
    app.config.update(SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"))
    i18n.init_i18n(app)
    with app.test_request_context("/", headers={"Accept-Language": "it"}):
        payload = _build_network_analytics_payload(_db(tmp_path), filter_day=2, filter_hour=1)
    assert payload["page_title"] == "Analisi della rete"
    assert [s["label"] for s in payload["stats"][:3]] == ["Nodi", "Archi", "Densità"]
    assert payload["secondary"]["labels"] == ["Giorno 1", "Giorno 2"]
    assert payload["stats"][5]["value"] == "Giorno 2" and payload["stats"][6]["value"] == "Ora 1"
    # identifiers used by the page logic stay untouched
    assert payload["network_type"] == "follow" and payload["granularity_options"][1]["value"] == "hour"
