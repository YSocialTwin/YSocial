"""A human participant can be added to an experiment whose runtime owns extra NOT NULL columns (Dating)."""

from sqlalchemy import Column, MetaData, Text, create_engine, text


def _engine(tmp_path, extra=True):
    from y_web.src.models import User_mgmt

    meta = MetaData()
    table = User_mgmt.__table__.to_metadata(meta)
    if extra:
        table.append_column(Column("match_recsys", Text, nullable=False))
    engine = create_engine(f"sqlite:///{tmp_path / 'exp.db'}")
    meta.create_all(engine)
    return engine


def test_a_runtime_column_the_model_does_not_know_is_filled(tmp_path):
    from y_web.src.experiment import helpers
    from y_web.src.models import User_mgmt

    engine = _engine(tmp_path)
    extra = helpers._required_unmapped_columns(engine)
    assert extra == {"match_recsys": ""}
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
            text("select id, username, match_recsys, round_actions from user_mgmt")
        ).one()
    assert tuple(row) == (7, "user1", "", 1)


def test_other_databases_are_left_alone(tmp_path):
    from y_web.src.experiment import helpers

    assert helpers._required_unmapped_columns(_engine(tmp_path, extra=False)) == {}
