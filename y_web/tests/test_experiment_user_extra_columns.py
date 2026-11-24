"""A human participant can be added to an experiment whose runtime owns extra NOT NULL columns (Dating)."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    MetaData,
    String,
    Text,
    create_engine,
    text,
)


def _engine(tmp_path, extra=True):
    from y_web.src.models import User_mgmt

    meta = MetaData()
    table = User_mgmt.__table__.to_metadata(meta)
    if extra:
        table.append_column(Column("match_recsys", Text, nullable=False))
        table.append_column(Column("status", String(16), nullable=False))
        table.append_constraint(
            CheckConstraint(
                "status IN ('active', 'paused', 'left')", name="ck_user_status"
            )
        )
    engine = create_engine(f"sqlite:///{tmp_path / 'exp.db'}")
    meta.create_all(engine)
    return engine


def test_a_runtime_column_the_model_does_not_know_is_filled(tmp_path):
    from y_web.src.experiment import helpers
    from y_web.src.models import User_mgmt

    engine = _engine(tmp_path)
    extra = helpers._required_unmapped_columns(engine)
    assert extra == {"match_recsys": "", "status": "active"}
    user = User_mgmt(
        id=7,
        username="user1",
        email="user1@example.org",
        password="x",
        user_type="user",
        leaning="neutral",
        age=0,
        recsys_type="default",
        frecsys_type="default",
        language="en",
        round_actions=1,
        toxicity="no",
        joined_on=0,
    )
    helpers._insert_user_with_extra_columns(engine, user, extra)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select id, username, match_recsys, status, round_actions from user_mgmt"
            )
        ).one()
    assert tuple(row) == (7, "user1", "", "active", 1)


def test_other_databases_are_left_alone(tmp_path):
    from y_web.src.experiment import helpers

    assert helpers._required_unmapped_columns(_engine(tmp_path, extra=False)) == {}


def test_a_participant_whose_account_id_is_taken_gets_the_next_free_id(
    tmp_path, monkeypatch
):
    """The account id (8) already belongs to an agent of the experiment: the participant is added under a new id."""
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from y_web.platforms import registry
    from y_web.src.experiment import helpers
    from y_web.src.models import User_mgmt

    engine = _engine(tmp_path, extra=False)
    with engine.begin() as connection:
        for i in range(1, 11):
            connection.execute(
                text(
                    "insert into user_mgmt (id, username, password, user_type, joined_on, cover_image) values (:i, :u, 'x', 'user', 0, '')"
                ),
                {"i": i, "u": f"agent{i}"},
            )
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(
        helpers, "open_experiment_session", lambda exp: (Session(), engine)
    )
    monkeypatch.setattr(
        registry,
        "resolve",
        lambda exp: SimpleNamespace(admin_view_session_keys=()),
    )
    kwargs = dict(email="p@y.org", password="x", joined_on=0)
    user, created = helpers._ensure_experiment_user(
        SimpleNamespace(), user_id=8, username="paperino", **kwargs
    )
    assert created and user.username == "paperino" and user.id == 11
    # a free account id is still used as is
    free, _ = helpers._ensure_experiment_user(
        SimpleNamespace(), user_id=50, username="pluto", **kwargs
    )
    assert free.id == 50
    # and the same person is found again, not duplicated
    again, created = helpers._ensure_experiment_user(
        SimpleNamespace(), user_id=8, username="paperino", **kwargs
    )
    assert not created and again.id == 11
