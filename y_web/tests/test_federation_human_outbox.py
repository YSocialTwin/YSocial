"""H5: cross-posts of the people enrolled in a World Simulation: destinations, text, delivery through the gateways (fakes)."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import human_outbox as ho  # noqa: E402
from y_web.src.federation import humans
from y_web.tests.test_federation_humans import Offline, make, user  # noqa: E402,F401
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)


def test_rule_text_shapes_and_cuts_for_each_platform():
    long = "word " * 200
    assert (
        len(ho.rule_text("microblogging", long)) <= 280
        and ho.rule_text("dating", long).count("word") <= 40
    )
    forum = ho.rule_text("forum", "I love the new park downtown. Everyone should go.")
    assert forum.startswith("I love the new park downtown.\nI love the new park")
    assert (
        ho.rule_text("microblogging", "  two   spaces\nand a line ")
        == "two spaces and a line"
    )
    assert ho.rule_text("photo_sharing", "") == ""


def test_rule_text_is_the_rule_of_the_agents_clients():
    import importlib.util
    import pathlib

    path = pathlib.Path("external/YClient/y_client/federation.py")
    if not path.exists():
        pytest.skip("YClient is not checked out")
    spec = importlib.util.spec_from_file_location("client_federation", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.LIMITS == ho.LIMITS
    for dest in ho.LIMITS:
        for text in (
            "hello world",
            "A title here. Then the body, long " * 20,
            "x" * 500,
        ):
            assert ho.rule_text(dest, text) == mod.rule_text(dest, text)


def enrolled(world_fixture, members=("forum", "microblogging")):
    fed, tmp = make(world_fixture)
    humans.enrol(fed, user(), list(members), offline=Offline())
    return fed, world_fixture[1]


def test_context_and_destinations_only_for_an_enrolled_person(world):
    fed, exps = enrolled(world)
    ctx = ho.context_for(exps["forum"], 7)
    assert (
        ctx.member == "forum"
        and ctx.human_id == "human:7"
        and ctx.destinations == {"microblogging": "microblogging"}
    )
    assert ho.destinations_for(exps["microblogging"], 7) == [
        {"member": "forum", "platform_type": "forum", "label": "forum"}
    ]
    assert (
        ho.context_for(exps["forum"], 8) is None
        and ho.destinations_for(exps["forum"], 8) == []
    )
    humans.unenrol(fed, 7)
    assert ho.context_for(exps["forum"], 7) is None


def test_requested_members_outside_the_enrolment_are_dropped_and_text_is_adapted(world):
    _, exps = enrolled(world)
    ctx = ho.context_for(exps["forum"], 7)
    out = ho.crosspost_to(
        ctx, ["microblogging", "dating", "ghost", "forum"], "hello " * 80
    )
    assert [t["member"] for t in out] == ["microblogging"] and len(
        out[0]["text"]
    ) <= 280
    assert ho.crosspost_to(ctx, [], "x") == [] and ho.requested_members(
        ["a, b", "c"]
    ) == ["a", "b", "c"]


def test_a_pending_dating_account_is_not_a_destination_until_confirmed(world):
    fed, exps = enrolled(world)
    from y_web.src.models.admin import FederationHuman

    row = FederationHuman.query.first()
    state = json.loads(row.members_json)
    state["forum"]["created"] = False
    row.members_json = json.dumps(state)
    from y_web import db

    db.session.commit()
    assert ho.context_for(exps["forum"], 7) is None
    assert ho.enrolment_of(exps["forum"], 7)[1] == "forum"
    assert (
        humans.confirm_account(fed, 7, "forum") is True
        and ho.context_for(exps["forum"], 7) is not None
    )


class Recorder:
    def __init__(self, answer=(200, {"ok": True})):
        self.requests, self.answer = [], answer

    def __call__(self, spec, request):
        self.requests.append((spec.platform_type, request))
        return self.answer


def test_try_deliver_sends_the_action_with_crosspost_to_through_the_gateway(world):
    _, exps = enrolled(world)
    rec = Recorder()
    sent = ho.try_deliver(
        exps["forum"],
        user(),
        ["microblogging"],
        "A title. And a body.",
        lambda t: ho.forum_post("A title. And a body.", t),
        only="forum",
        offline=rec,
    )
    assert sent is True
    platform, request = rec.requests[0]
    assert platform == "forum" and request["op"] == "act"
    action = request["body"]["actions"][0]
    assert action["action"] == "post" and action["crosspost_to"] == [
        {"member": "microblogging", "text": "A title. And a body."}
    ]
    assert request["body"]["username"] == "giulio" and request["body"][
        "email"
    ].endswith("@human.invalid")
    rec2 = Recorder()
    assert (
        ho.try_deliver(
            exps["microblogging"],
            user(),
            ["forum"],
            "hi there",
            lambda t: ho.micro_post("hi there", t),
            only="microblogging",
            offline=rec2,
        )
        is True
    )
    body = rec2.requests[0][1]["body"]
    assert (
        rec2.requests[0][1]["op"] == "actions"
        and isinstance(body["account_id"], int)
        and body["actions"][0]["type"] == "post"
    )
    assert body["actions"][0]["crosspost_to"][0]["member"] == "forum"


def test_nothing_changes_for_a_person_who_is_not_enrolled_or_picked_nothing(world):
    _, exps = enrolled(world)
    rec = Recorder()
    build = lambda t: ho.forum_post("x", t)  # noqa: E731
    assert (
        ho.try_deliver(
            exps["forum"], user(8, "ann"), ["microblogging"], "x", build, offline=rec
        )
        is None
    )
    assert ho.try_deliver(exps["forum"], user(), [], "x", build, offline=rec) is None
    assert (
        ho.try_deliver(exps["forum"], user(), ["dating"], "x", build, offline=rec)
        is None
    )
    assert (
        ho.try_deliver(
            exps["forum"],
            user(),
            ["microblogging"],
            "x",
            build,
            only="microblogging",
            offline=rec,
        )
        is None
    )
    assert rec.requests == []
    assert (
        ho.targets_for_request(exps["forum"], user(8, "ann"), ["microblogging"], "x")
        == []
    )


def test_a_refusal_or_an_unreachable_gateway_is_false_never_a_second_write(world):
    _, exps = enrolled(world)
    build = lambda t: ho.forum_post("x", t)  # noqa: E731
    assert (
        ho.try_deliver(
            exps["forum"],
            user(),
            ["microblogging"],
            "x",
            build,
            offline=Recorder((403, {"ok": False})),
        )
        is False
    )

    def boom(spec, request):
        raise RuntimeError("down")

    assert (
        ho.try_deliver(
            exps["forum"], user(), ["microblogging"], "x", build, offline=boom
        )
        is False
    )


def test_photo_and_im_actions_have_the_gateway_shape():
    assert ho.photo_post(
        "cap", [{"member": "x", "text": "t"}], image_base64="AA==", extension="png"
    ) == {
        "type": "post_photo",
        "caption": "cap",
        "crosspost_to": [{"member": "x", "text": "t"}],
        "image_base64": "AA==",
        "extension": "png",
    }
    assert (
        ho.photo_share("p1", "", [])["type"] == "share"
        and ho.micro_share(3, "", [])["post_id"] == 3
    )
    assert ho.im_action("post", [], chat_id="c", text="hi") == {
        "type": "post",
        "chat_id": "c",
        "text": "hi",
    }
    assert (
        ho.im_action(
            "forward", [{"member": "m", "text": "t"}], forward_of_message_id="9"
        )["crosspost_to"][0]["member"]
        == "m"
    )


def test_integrated_a_human_post_reaches_the_destination_exactly_once(world):
    """YWeb -> (fake) forum gateway -> crosspost.v1 -> in-memory fake coordinator -> (fake) microblogging member."""
    from ysocial_federation.envelope import Envelope
    from ysocial_federation.testing.fake_coordinator import FakeCoordinator
    from ysocial_federation.testing.memory_adapter import MemoryAdapter

    _, exps = enrolled(world)
    ctx = ho.context_for(exps["forum"], 7)
    asked = []

    def gateway(
        spec, request
    ):  # what the forum gateway does with ``crosspost_to``: remember it for the next export
        asked.extend(request["body"]["actions"][0]["crosspost_to"])
        return 200, {"ok": True}

    text = "A title. The words of a person, long enough to be adapted."
    assert (
        ho.try_deliver(
            exps["forum"],
            user(),
            ["microblogging"],
            text,
            lambda t: ho.forum_post(text, t),
            only="forum",
            offline=gateway,
        )
        is True
    )
    assert [t["member"] for t in asked] == ["microblogging"]

    with FakeCoordinator(["forum", "microblogging"]) as fed:
        clients = {m: fed.client(m) for m in fed.members}
        for c in clients.values():
            c.hello("exp", 0)
        content = {
            "global_agent_id": ctx.human_id,
            "source_ref": "ysocial://1/forum/post/5",
            "kind": "post",
            "text_excerpt": asked[0]["text"],
            "image_ref": None,
            "topics": [],
            "lang": "en",
            "target_account_id": ctx.accounts["microblogging"],
        }
        env = Envelope.create(
            1, "forum", "microblogging", 2, 0, "crosspost.v1", content
        )
        clients["forum"].outbox(2, [env])
        clients["forum"].outbox(
            2, [env]
        )  # a retry of the same export: the bus keeps one copy
        destination = MemoryAdapter(platform="microblogging", member="microblogging")
        got = clients["microblogging"].inbox(3)
        assert (
            len(got) == 1
            and got[0].payload["global_agent_id"] == "human:7"
            and got[0].payload["text_excerpt"] == asked[0]["text"]
        )
        report = destination.ingest_inbox(3, got)
        assert report.materialized == 1
        clients["microblogging"].ack(3, [e.fed_msg_id for e in got])
        assert clients["microblogging"].inbox(3) == []
        assert (
            destination.ingest_inbox(3, got).duplicates == 1
            and len(destination.materialized) == 1
        )


def test_lifecycle_hooks_write_the_token_and_start_the_gateway_only_with_humans(
    world, monkeypatch
):
    from y_web.src.federation import human_gateways as hg
    from y_web.src.federation import service

    fed, tmp = make(world)
    exps = world[1]
    micro = next(e for r, e in service.members_of(fed) if r.member == "microblogging")
    forum = next(e for r, e in service.members_of(fed) if r.member == "forum")
    cfg = tmp / "experiments" / "microblogging" / "config_server.json"
    humans.prepare_member(fed, micro)
    assert "human_gateway" not in json.loads(
        cfg.read_text()
    )  # nobody enrolled: untouched
    started = []
    monkeypatch.setattr(
        hg,
        "start_gateway",
        lambda *a, **k: started.append((a[0], k.get("server_url"))) or 4242,
    )
    assert humans.after_server_started(fed, forum) is None and started == []
    humans.enrol(fed, user(), ["forum", "microblogging"], offline=Offline())
    humans.prepare_member(fed, micro)
    assert json.loads(cfg.read_text())["human_gateway"]["token"]
    assert (
        humans.after_server_started(fed, forum) == 4242
        and started[0][0] == "forum"
        and started[0][1].startswith("http://")
    )
    assert (
        humans.after_server_started(fed, micro) is None
    )  # microblogging has no process
    stopped = []
    monkeypatch.setattr(hg, "is_running", lambda folder: True)
    monkeypatch.setattr(
        hg, "stop_gateway", lambda folder, pid=None: stopped.append(str(folder)) or True
    )
    assert humans.after_server_stopped(forum) is True and len(stopped) == 1
