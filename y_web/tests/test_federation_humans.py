"""H3: enrolment of people in a World Simulation: identity, accounts through the gateways (fakes), the running coordinator."""

import json
import os
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import human_gateways, humans, service  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)


class FakeCoordinator:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def add_identity(self, gid, kind, accounts):
        if self.fail:
            raise RuntimeError("identity_conflict")
        self.calls.append((gid, kind, accounts))
        return {"created": True}


class Offline:
    """Stands in for the runtime's offline script: records what would be asked, answers with account ids."""

    def __init__(self, fail_for=()):
        self.requests, self.fail_for, self.next = [], set(fail_for), 100

    def __call__(self, spec, request):
        if spec.platform_type in self.fail_for:
            raise human_gateways.GatewayUnavailable("no server and no offline script")
        self.requests.append((spec.platform_type, request))
        self.next += 1
        return 200, {"ok": True, "account_id": self.next, "created": True}


def user(uid=7, name="giulio"):
    return SimpleNamespace(id=uid, username=name)


def make(world_fixture):
    app, exps, tmp = world_fixture
    return service.create_federation("w", list(exps.values()), owner="admin", seed=1), tmp


def test_enrol_records_identity_links_and_asks_each_gateway(world):
    from y_web.src.models.admin import FederationHuman, FederationIdentityLink

    fed, tmp = make(world)
    off = Offline()
    h = humans.enrol(fed, user(), ["forum", "microblogging"], offline=off)
    assert h.human_id == "human:7" and h.status == "active"
    assert json.loads(h.members_json) == {"forum": {"account_id": "101", "created": True},
                                          "microblogging": {"account_id": "102", "created": True}}
    kinds = {p: r for p, r in off.requests}
    assert kinds["microblogging"]["op"] == "ensure" and kinds["microblogging"]["body"]["human_id"] == "human:7"
    assert kinds["forum"]["op"] == "register" and kinds["forum"]["body"]["account"]["username"] == "giulio"
    links = FederationIdentityLink.query.filter_by(federation_pk=fed.id, global_agent_id="human:7").all()
    assert sorted((l.member, l.local_account_id) for l in links) == [("forum", "101"), ("microblogging", "102")]
    config = json.load(open(os.path.join(fed.folder, "federation.json")))
    assert {"global_agent_id": "human:7", "member": "forum", "local_account_id": "101", "eligible": True} in config["identity"]
    assert FederationHuman.query.count() == 1


def test_stopped_federation_does_not_touch_member_configurations_and_running_one_does(world):
    fed, tmp = make(world)
    humans.enrol(fed, user(), ["forum"], offline=Offline())
    cfg = tmp / "experiments" / "forum" / "config_server.json"
    assert "federation" not in json.loads(cfg.read_text())
    fed.status = "running"
    coord = FakeCoordinator()
    humans.enrol(fed, user(8, "ann"), ["forum"], offline=Offline(), coordinator=coord)
    section = json.loads(cfg.read_text())["federation"]
    assert section["accounts"] == {"human:7": "101", "human:8": "101"}
    assert coord.calls == [("human:8", "human", [{"member": "forum", "local_account_id": section["accounts"]["human:8"]}])]


def test_enrol_is_idempotent_and_does_not_ask_again(world):
    fed, _ = make(world)
    off = Offline()
    humans.enrol(fed, user(), ["forum"], offline=off)
    humans.enrol(fed, user(), ["forum"], offline=off)
    assert len(off.requests) == 1


def test_a_failing_gateway_leaves_nothing_recorded(world):
    from y_web.src.models.admin import FederationHuman, FederationIdentityLink

    fed, _ = make(world)
    with pytest.raises(humans.HumanEnrolmentError) as err:
        humans.enrol(fed, user(), ["forum", "microblogging"], offline=Offline(fail_for={"microblogging"}))
    assert err.value.errors[0]["code"] == "gateway_unavailable"
    assert FederationHuman.query.count() == 0
    assert FederationIdentityLink.query.filter_by(global_agent_id="human:7").count() == 0


def test_the_coordinator_refusal_rolls_the_enrolment_back(world):
    from y_web.src.models.admin import FederationHuman, FederationIdentityLink

    fed, _ = make(world)
    fed.status = "running"
    with pytest.raises(humans.HumanEnrolmentError) as err:
        humans.enrol(fed, user(), ["forum"], offline=Offline(), coordinator=FakeCoordinator(fail=True))
    assert err.value.errors[0]["code"] == "coordinator_refused"
    assert FederationHuman.query.count() == 0 and FederationIdentityLink.query.filter_by(global_agent_id="human:7").count() == 0


@pytest.mark.parametrize("members,code", [([], "no_member"), (["dating"], "unknown_member")])
def test_invalid_selections(world, members, code):
    fed, _ = make(world)
    with pytest.raises(humans.HumanEnrolmentError) as err:
        humans.enrol(fed, user(), members, offline=Offline())
    assert err.value.errors[0]["code"] == code


def test_hpc_microblogging_is_enrolled_through_the_ysimulator_script(world):
    from y_web import db

    fed, _ = make(world)
    row, exp = [(r, e) for r, e in service.members_of(fed) if r.member == "microblogging"][0]
    exp.simulator_type = "HPC"
    db.session.commit()
    off = Offline()
    h = humans.enrol(fed, user(), ["microblogging"], offline=off)
    assert json.loads(h.members_json) == {"microblogging": {"account_id": "101", "created": True}}
    (platform, request), = off.requests
    assert platform == "microblogging" and request["op"] == "ensure"
    assert request["body"] == {"human_key": "u7", "username": "giulio", "language": request["body"]["language"], "human_id": "human:7"}


def test_the_hpc_gateway_uses_the_ysimulator_script_for_every_request(tmp_path):
    seen = []

    def runner(spec, request):
        seen.append((spec.repo, spec.script, request))
        return 200, {"ok": True}

    gw = human_gateways.RuntimeGateway("microblogging", tmp_path, offline=runner, hpc=True)
    gw.actions("a1b2", "ann", "u7", [{"type": "post", "text": "hi"}])
    assert seen == [("YSimulator", "run_human_gateway.py", {"op": "actions", "body": {"account_id": "a1b2", "actions": [{"type": "post", "text": "hi"}]}})]
    with pytest.raises(human_gateways.GatewayUnavailable):
        human_gateways.RuntimeGateway("forum", tmp_path, hpc=True)


def test_unenrol_keeps_accounts_and_links_and_drops_the_configuration_entry(world):
    from y_web.src.models.admin import FederationIdentityLink

    fed, tmp = make(world)
    fed.status = "running"
    humans.enrol(fed, user(), ["forum"], offline=Offline(), coordinator=FakeCoordinator())
    assert humans.unenrol(fed, 7) is True and humans.unenrol(fed, 7) is False
    assert FederationIdentityLink.query.filter_by(global_agent_id="human:7").count() == 1
    assert humans.accounts_by_member(fed) == {}
    assert "accounts" not in json.loads((tmp / "experiments" / "forum" / "config_server.json").read_text())["federation"]


def test_pending_account_is_confirmed_once(world):
    from y_web import db
    from y_web.src.models.admin import FederationHuman

    fed, _ = make(world)
    db.session.add(FederationHuman(federation_pk=fed.id, user_id=3, human_id="human:3", status="active",
                                   members_json=json.dumps({"forum": {"account_id": "abc", "created": False}})))
    db.session.commit()
    assert humans.confirm_account(fed, 3, "forum") is True and humans.confirm_account(fed, 3, "forum") is False
    assert humans.accounts_by_member(fed) == {"forum": {"human:3": "abc"}}


# -- the gateway clients -------------------------------------------------------------------------------
class Session:
    def __init__(self, status=200, payload=None):
        self.calls, self.status, self.payload = [], status, payload or {"ok": True, "account_id": 5}

    def post(self, url, json=None, headers=None, timeout=0):
        self.calls.append((url, json, headers))
        return SimpleNamespace(status_code=self.status, json=lambda: self.payload)


def test_microblogging_gateway_uses_the_token_of_the_server_configuration(tmp_path):
    cfg = tmp_path / "config_server.json"
    cfg.write_text(json.dumps({"host": "127.0.0.1", "port": 5010}))
    token = human_gateways.set_microblogging_token(cfg)
    assert json.loads(cfg.read_text())["human_gateway"]["token"] == token and human_gateways.set_microblogging_token(cfg) == token
    (tmp_path / "ray_ready.temp").write_text("")
    s = Session()
    out = human_gateways.RuntimeGateway("microblogging", tmp_path, server_config=cfg, session=s).ensure("u7", "ann", "human:7")
    assert out == (200, {"ok": True, "account_id": 5})
    url, body, headers = s.calls[0]
    assert url == "http://127.0.0.1:5010/gateway/v1/humans/ensure" and headers == {"X-YServer-Gateway-Token": token}
    assert body["human_id"] == "human:7" and body["human_key"] == "u7"


def test_running_server_without_gateway_is_never_written_offline(tmp_path):
    (tmp_path / "ray_ready.temp").write_text("")
    with pytest.raises(human_gateways.GatewayUnavailable):
        human_gateways.RuntimeGateway("photo_sharing", tmp_path, offline=lambda *a: (200, {})).ensure("7", "ann", "human:7")


def test_process_gateways_read_state_and_token_files(tmp_path):
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])  # a live pid that is not the test runner
    (tmp_path / human_gateways.STATE_FILE).write_text(json.dumps({"host": "127.0.0.1", "port": 5111, "pid": proc.pid}))
    token = human_gateways.write_token(tmp_path)
    assert oct(os.stat(tmp_path / human_gateways.TOKEN_FILE).st_mode & 0o777) == "0o600"
    s = Session()
    human_gateways.RuntimeGateway("photo_sharing", tmp_path, session=s).ensure("7", "ann", "human:7")
    url, body, headers = s.calls[0]
    assert url == "http://127.0.0.1:5111/v1/humans/ensure" and headers == {"X-YPS-Gateway-Token": token}
    assert body == {"human_key": "7", "username": "ann", "language": None}
    s2 = Session()
    human_gateways.RuntimeGateway("forum", tmp_path, session=s2).ensure("u7", "ann", "human:7", "it")
    assert s2.calls[0][0].endswith("/register") and s2.calls[0][2] == {"X-YGateway-Token": token}
    assert s2.calls[0][1]["account"]["language"] == "it"
    assert human_gateways.stop_gateway(tmp_path) is True
    proc.wait(timeout=10)
    assert not (tmp_path / human_gateways.TOKEN_FILE).exists() and not (tmp_path / human_gateways.STATE_FILE).exists()


def test_human_table_has_its_own_idempotent_migration(app):
    from sqlalchemy import create_engine, inspect

    from y_web.src.system.startup_migrations import ensure_federation_human_tables, ensure_federation_tables

    engine = create_engine("sqlite://")
    assert "federation_human" not in ensure_federation_tables(engine)  # the first release's list is unchanged
    assert ensure_federation_human_tables(engine) == ["federation_human"] and ensure_federation_human_tables(engine) == []
    assert "federation_human" in inspect(engine).get_table_names()
