"""Participants' reactions kept apart (``isolate_participant_reactions``) and the server-side interaction switches."""

from types import SimpleNamespace

import pytest
from flask import g, request

from y_web import db
from y_web.src.content import reaction_counts as rc
from y_web.src.models import Admin_users, Post, Reactions, Rounds, User_mgmt


@pytest.fixture
def world(app):
    with app.app_context():
        rnd = Rounds(day=0, hour=0)
        db.session.add(rnd)
        for name in ("p1", "p2"):
            db.session.add(
                Admin_users(
                    username=name,
                    email=f"{name}@x.org",
                    password="x",
                    role="user",
                    last_seen="2026-01-01",
                )
            )
        users = {n: User_mgmt(username=n, password="x", joined_on=0) for n in ("p1", "p2", "bot")}
        db.session.add_all(users.values())
        db.session.commit()
        post = Post(tweet="hello", round=rnd.id, user_id=users["bot"].id, comment_to=-1)
        db.session.add(post)
        db.session.commit()
        for who, kind in (("bot", "like"), ("p1", "like"), ("p2", "like"), ("p2", "dislike")):
            db.session.add(Reactions(round=rnd.id, user_id=users[who].id, post_id=post.id, type=kind))
        db.session.commit()
        yield SimpleNamespace(app=app, post=post.id, users={n: u.id for n, u in users.items()})


def _counts(world, monkeypatch, viewer, isolate):
    monkeypatch.setattr(
        "y_web.routes.social.helpers._load_ui_settings",
        lambda exp_id: {"isolate_participant_reactions": isolate},
    )
    monkeypatch.setattr(rc, "current_user", SimpleNamespace(username=viewer))
    with world.app.test_request_context("/7/feed"):
        request.view_args = {"exp_id": 7}
        g.pop(rc._CACHE, None)  # a real request has its own application context, hence its own cache
        return rc.count_reactions(world.post, "like"), rc.count_reactions(world.post, "dislike")


def test_off_by_default_everybody_sees_everything(world, monkeypatch):
    for viewer in ("p1", "p2", "bot"):
        assert _counts(world, monkeypatch, viewer, False) == (3, 1)


def test_on_a_participant_sees_the_crowd_plus_their_own(world, monkeypatch):
    assert _counts(world, monkeypatch, "p1", True) == (2, 0)  # bot + own like; p2's reactions are hidden
    assert _counts(world, monkeypatch, "p2", True) == (2, 1)  # bot + own like; own dislike


def test_on_the_others_see_only_the_crowd(world, monkeypatch):
    assert _counts(world, monkeypatch, "bot", True) == (1, 0)
    assert _counts(world, monkeypatch, "nobody", True) == (1, 0)


def test_isolated_reactions_do_not_move_the_popularity(world, monkeypatch):
    monkeypatch.setattr(
        "y_web.routes.social.helpers._load_ui_settings",
        lambda exp_id: {"isolate_participant_reactions": True},
    )
    with world.app.test_request_context("/7/react_to_content"):
        request.view_args = {"exp_id": 7}
        assert rc.reaction_is_isolated(world.users["p1"]) is True
        assert rc.reaction_is_isolated(world.users["bot"]) is False
    monkeypatch.setattr(
        "y_web.routes.social.helpers._load_ui_settings",
        lambda exp_id: {"isolate_participant_reactions": False},
    )
    with world.app.test_request_context("/7/react_to_content"):
        request.view_args = {"exp_id": 7}
        assert rc.reaction_is_isolated(world.users["p1"]) is False


def test_without_a_request_nothing_is_hidden(world):
    with world.app.app_context():
        assert rc.hidden_reactor_ids() == frozenset()


@pytest.mark.parametrize(
    "ui, action, allowed",
    [
        ({}, "like", True),
        ({"interaction_like": False}, "like", False),
        ({"interaction_like": False}, "dislike", True),
        ({"interaction_dislike": False}, "dislike", False),
        ({"interactions_enabled": False}, "like", False),
        ({"interactions_enabled": False}, "dislike", False),
    ],
)
def test_interaction_switches_are_enforced_on_the_server(ui, action, allowed):
    from y_web.routes.interactions.common import _interaction_allowed

    assert _interaction_allowed(ui, action) is allowed


def test_the_new_setting_is_known_and_off_by_default():
    from y_web.src.experiment.frontend_defaults import DEFAULT_SETTINGS

    assert DEFAULT_SETTINGS["isolate_participant_reactions"] is False
