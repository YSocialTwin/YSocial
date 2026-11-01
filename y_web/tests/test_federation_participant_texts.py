"""P7 (YWeb): per-destination text in the composers, and the notice of the cross-posts waiting for a stopped platform (fakes)."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import human_outbox as ho, humans, pending_notice  # noqa: E402
from y_web.tests.test_federation_humans import Offline, make, user  # noqa: E402,F401
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)


def ctx():
    return ho.HumanContext(None, "microblogging", "microblogging", "human:7", 7, "1", {},
                           {"forum": "forum", "dating": "dating", "photo_sharing": "photo_sharing"})


# -- D5 b: the edited text ------------------------------------------------------------------------------
def test_without_edits_the_text_is_the_rule_text():
    assert ho.crosspost_to(ctx(), ["forum"], "Nice day. Really.", overrides={}) == [{"member": "forum", "text": ho.rule_text("forum", "Nice day. Really.")}]


def test_an_edited_text_replaces_the_rule_text_and_is_cut_to_the_limit_of_each_platform():
    long = "word " * 700
    out = {t["member"]: t["text"] for t in ho.crosspost_to(ctx(), ["dating", "forum", "photo_sharing"], "hi",
                                                           overrides={"dating": long, "forum": long, "photo_sharing": "  my   caption "})}
    assert len(out["dating"]) <= ho.LIMITS["dating"] and out["photo_sharing"] == "my caption"
    assert len(out["forum"]) <= ho.LIMITS["forum"] and "\n" in out["forum"]  # a title line is added to a one-line edit


def test_empty_edit_falls_back_and_the_server_alone_decides_the_destinations():
    out = ho.crosspost_to(ctx(), ["dating", "elsewhere"], "plain words", overrides={"dating": "   ", "forum": "not requested", "elsewhere": "x"})
    assert out == [{"member": "dating", "text": "plain words"}]


def test_edits_are_read_from_the_request_in_every_shape_and_garbage_means_none(world):
    app, _, _ = world
    c = ctx()
    edit = {"forum": "from the page"}
    with app.test_request_context("/x?crosspost_texts=" + json.dumps(edit)):
        assert ho.crosspost_to(c, ["forum"], "t")[0]["text"].endswith("from the page")
    with app.test_request_context("/x", method="POST", json={"crosspost_texts": edit}):
        assert ho.crosspost_to(c, ["forum"], "t")[0]["text"].endswith("from the page")
    with app.test_request_context("/x", method="POST", data={"crosspost_texts": json.dumps({"dating": "d"})}):
        assert ho.crosspost_to(c, ["dating"], "t")[0]["text"] == "d"
    for bad in ("not json", "[1]", '{"forum": 3}'):
        with app.test_request_context("/x?crosspost_texts=" + bad):
            assert ho.crosspost_to(c, ["forum"], "t")[0]["text"] == ho.rule_text("forum", "t")
    assert ho.request_overrides() == {}  # outside a request


def test_suggestions_are_the_rule_text_and_the_limit(world, monkeypatch):
    monkeypatch.setattr(ho, "context_for", lambda e, u: ctx() if u else None)
    got = ho.suggestions_for(1, 7, "hello there", ["dating", "forum", "unknown"])
    assert got == {"dating": {"text": "hello there", "limit": 200}, "forum": {"text": ho.rule_text("forum", "hello there"), "limit": 2000}}
    assert ho.suggestions_for(1, None, "x") == {}


def test_the_suggestion_endpoint_returns_json_and_never_fails(world, monkeypatch):
    from y_web.routes.interactions import common

    app, _, _ = world
    monkeypatch.setattr(common, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(ho, "context_for", lambda e, u: ctx())
    view = common.federation_crosspost_suggest.__wrapped__
    with app.test_request_context("/1/federation/crosspost_suggest?text=hi&crosspost=dating"):
        assert view(1).get_json() == {"texts": {"dating": {"text": "hi", "limit": 200}}}
    monkeypatch.setattr(ho, "context_for", lambda e, u: 1 / 0)
    with app.test_request_context("/1/federation/crosspost_suggest?text=hi"):
        assert view(1).get_json() == {"texts": {}}


# -- the template ----------------------------------------------------------------------------------------
def _render(dests, waiting):
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader("y_web/templates"), autoescape=True)
    env.globals.update(ws_destinations=lambda e: dests, ws_pending=lambda e: waiting, url_for=lambda endpoint, **k: "/static/" + k["filename"],
                       _=lambda s, **k: s % k if k else s)
    return env.get_template("shared/world_simulation_crosspost.html").render(ws_exp=3)


def test_each_destination_has_an_editable_text_and_the_experiment_id_for_the_suggestions():
    html = _render([{"member": "forum", "platform_type": "forum"}, {"member": "dating", "platform_type": "dating"}], [])
    assert html.count("<textarea") == 2 and 'data-ws-exp="3"' in html and "Text on Forum" in html and "data-ws-pending" not in html


def test_the_pending_notice_lists_the_waiting_cross_posts_with_their_attribution():
    waiting = [{"text": "first", "attribution": "", "source": "Forum"}, {"text": "second", "attribution": "↪ ann @ Forum: «q»", "source": "Forum"}]
    html = _render([], waiting)
    assert "2 cross-posts are waiting and will appear when this platform restarts" in html and "first" in html and "↪ ann @ Forum: «q»" in html
    assert "<textarea" not in html and "world-simulation-crosspost.js" not in html
    assert _render([], []).strip() == ""


# -- the notice ------------------------------------------------------------------------------------------
class FakeCoordinator:
    def __init__(self, items=None, fail=False):
        self.calls, self.items, self.fail = [], items or [], fail

    def pending(self, account):
        self.calls.append(str(account))
        if self.fail:
            raise RuntimeError("down")
        return self.items


@pytest.fixture
def enrolled(world):
    from y_web import db
    from y_web.src.models import Exps

    app, exps, tmp = world
    pending_notice._cache.clear()
    fed, _ = make(world)
    humans.enrol(fed, user(), ["forum", "microblogging"], offline=Offline())
    fed.status = "running"
    db.session.commit()
    exp = db.session.get(Exps, exps["forum"])
    exp.server_pid = None
    db.session.commit()
    return fed, exps, exp


def _factory(fake, seen=None):
    def make_client(fed, member):
        if seen is not None:
            seen.append(member)
        return fake
    return make_client


def test_a_stopped_member_of_a_running_world_simulation_shows_what_is_waiting(enrolled):
    fed, exps, _ = enrolled
    item = {"fed_msg_id": "m1", "source_member": "microblogging", "text_excerpt": "hello", "kind": "post",
            "quoted": {"author_name": "ann", "member": "microblogging", "text_excerpt": "orig"}}
    fake, seen = FakeCoordinator([item, {"fed_msg_id": "m2", "source_member": "microblogging", "text_excerpt": "again"}]), []
    got = pending_notice.pending_for(exps["forum"], 7, client_factory=_factory(fake, seen))
    assert [g["text"] for g in got] == ["hello", "again"] and got[0]["attribution"] == "↪ ann @ Microblogging: «orig»" and got[1]["attribution"] == ""
    assert seen == ["forum"] and fake.calls == ["101"]


def test_no_request_unless_enrolled_coordinator_up_and_server_stopped(enrolled):
    from y_web import db

    fed, exps, exp = enrolled
    fake = FakeCoordinator([{"text_excerpt": "x"}])
    f = _factory(fake)
    assert pending_notice.pending_for(exps["forum"], 99, client_factory=f) == []  # not enrolled
    assert pending_notice.pending_for(exps["forum"], None, client_factory=f) == []
    assert pending_notice.pending_for(99999, 7, client_factory=f) == []  # not a member of any World Simulation
    exp.server_pid = 4242  # the server runs: the platform shows its own posts
    db.session.commit()
    assert pending_notice.pending_for(exps["forum"], 7, client_factory=f) == []
    exp.server_pid = None
    fed.status = "stopped"  # no coordinator to ask
    db.session.commit()
    assert pending_notice.pending_for(exps["forum"], 7, client_factory=f) == []
    assert fake.calls == []


def test_errors_mean_no_notice_and_the_answer_is_cached_a_few_seconds(enrolled):
    fed, exps, _ = enrolled
    assert pending_notice.pending_for(exps["forum"], 7, client_factory=_factory(FakeCoordinator(fail=True))) == []
    assert pending_notice.pending_for(exps["forum"], 7, client_factory=lambda f, m: 1 / 0) == []
    fake, now = FakeCoordinator([{"text_excerpt": "x"}]), [100.0]
    clock = lambda: now[0]  # noqa: E731
    for _ in range(3):
        assert len(pending_notice.pending_for(exps["forum"], 7, client_factory=_factory(fake), clock=clock)) == 1
    assert fake.calls == ["101"]
    now[0] += pending_notice.CACHE_SECONDS + 1
    pending_notice.pending_for(exps["forum"], 7, client_factory=_factory(fake), clock=clock)
    assert fake.calls == ["101", "101"]


def test_the_client_is_the_real_one_and_asks_pending_of_its_own_member(tmp_path):
    from ysocial_federation.client import CoordinatorClient

    assert callable(getattr(CoordinatorClient, "pending", None))
    (tmp_path / "federation_coordinator.json").write_text(json.dumps({"host": "127.0.0.1", "port": 1}))
    (tmp_path / "federation.token").write_text("t")
    client = pending_notice._client(SimpleNamespace(folder=str(tmp_path)), "forum")
    assert client.member == "forum"
