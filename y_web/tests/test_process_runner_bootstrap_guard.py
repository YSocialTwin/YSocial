import pytest

pytestmark = pytest.mark.unit

import json
import sqlite3

from y_web.src.simulation.process_runner import (
    _load_population_usernames,
    _population_bootstrap_completed,
)


def test_load_population_usernames_skips_pages(tmp_path):
    population_path = tmp_path / "population.json"
    population_path.write_text(
        json.dumps(
            {
                "agents": [
                    {"name": "alice", "is_page": 0},
                    {"name": "news", "is_page": 1},
                    {"name": "bob"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _load_population_usernames(str(population_path)) == ["alice", "bob"]


def test_population_bootstrap_completed_requires_all_registered_users(tmp_path):
    population_path = tmp_path / "population.json"
    population_path.write_text(
        json.dumps({"agents": [{"name": "alice"}, {"name": "bob"}]}),
        encoding="utf-8",
    )

    db_path = tmp_path / "experiment.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "create table user_mgmt (id integer primary key, username text not null)"
        )
        connection.execute("insert into user_mgmt (username) values (?)", ("alice",))
        connection.commit()

    assert not _population_bootstrap_completed(str(db_path), str(population_path))

    with sqlite3.connect(db_path) as connection:
        connection.execute("insert into user_mgmt (username) values (?)", ("bob",))
        connection.commit()

    assert _population_bootstrap_completed(str(db_path), str(population_path))
