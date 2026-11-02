"""The loop YWeb runs for the microblogging and the forum applies the federation hooks (World Simulation 1).

YWeb does not use `YClient.run_simulation`: `process_runner.run_simulation` and `agent_sampler.process_agent` drive the
slots. The hooks of the client loop (adopt_provisioned, filter_pool, scale_actions) were missing there: attention
multipliers never applied, inactive members kept acting, accounts the federation created for new agents were never
adopted. With a fake federation module these tests check each hook in the pieces and in the real `run_simulation`,
and that without a federation nothing changes."""

import random
import sys
import types
from collections import defaultdict
from types import SimpleNamespace

import pytest

from y_web.src.simulation import agent_sampler as sampler
from y_web.src.simulation import federation_hooks as hooks
from y_web.src.simulation import process_runner

NO_ARCHETYPES = {"enabled": False, "distribution": {}, "transitions": {}}


class FakeFederation:
    """Stands for `y_client.federation` with the federation on: the same four functions the client loops call."""

    def __init__(self, hidden=(), multipliers=None, provisioned=()):
        self.hidden, self.multipliers, self.provisioned = set(hidden), dict(multipliers or {}), list(provisioned)
        self.calls = []

    def enabled(self):
        return True

    def filter_pool(self, agents):
        self.calls.append("filter_pool")
        return [a for a in agents if a.user_id not in self.hidden] if self.hidden else agents

    def scale_actions(self, n, user_id):
        self.calls.append(("scale_actions", n, user_id))
        return int(round(n * self.multipliers.get(user_id, 1.0)))

    def adopt_provisioned(self, client):
        self.calls.append("adopt_provisioned")
        while self.provisioned:
            client.adopt_federated_account(self.provisioned.pop())


def make_agent(uid, round_actions=3):
    a = SimpleNamespace(
        name=f"u{uid}", user_id=uid, is_page=0, round_actions=round_actions, daily_activity_level=1,
        activity_profile="Always On", archetype="broadcaster", acted=[],
    )
    a.evaluate_stress_reward_churn = lambda tid, rng=None: False
    a.select_action = lambda tid, actions=None, **kw: a.acted.append(tid)
    a.reply = lambda tid=None: None
    return a


def make_client(agents, slots=1, days=1):
    cl = SimpleNamespace(
        agents=SimpleNamespace(agents=list(agents), remove_agent_by_ids=lambda ids: None),
        actions_likelihood={"POST": 1.0, "COMMENT": 1.0}, pages=[], config={"agents": {"probability_of_daily_follow": 0}},
        max_length_thread_reading=5, days=days, slots=slots, hourly_activity={str(h): 1.0 for h in range(24)},
        percentage_new_agents_iteration=0, agent_archetypes=NO_ARCHETYPES, adopted_accounts=[],
    )

    def adopt(account):
        agent = make_agent(account["user_id"])
        agent.activity_profile = None  # an agent loaded from the server has none: the loop gives it the default
        cl.agents.agents.append(agent)
        cl.adopted_accounts.append(account)
        return agent

    cl.adopt_federated_account = adopt
    state = {"slot": 0}
    cl.sim_clock = SimpleNamespace(
        get_current_slot=lambda: (state["slot"], state["slot"] // 24, state["slot"] % 24),
        increment_slot=lambda: state.update(slot=state["slot"] + 1),
    )
    cl.churn = lambda tid: None
    cl.save_agents = lambda path: None
    return cl


@pytest.fixture
def federation(monkeypatch):
    def install(fed):
        monkeypatch.setattr(hooks, "federation_module", lambda: fed)
        return fed

    return install


# ------------------------------------------------------------------------------------------------ no federation
def test_without_a_federation_the_hooks_return_their_inputs_and_draw_nothing(monkeypatch):
    monkeypatch.setattr(hooks, "federation_module", lambda: None)
    cl = make_client([make_agent(1)])
    pool = [make_agent(2)]
    state = random.getstate()
    assert hooks.filter_pool(pool) is pool
    assert hooks.scaled_round_actions(pool[0], 4) == 4
    assert hooks.adopt_provisioned(cl) == []
    users = defaultdict(list, {5: pool})
    assert hooks.prepare_slot(cl, ["x"], users, 5, lambda agents: 1 / 0) == (["x"], users, pool)
    assert random.getstate() == state


def test_the_module_is_none_when_the_client_package_has_no_federation_or_it_is_off(monkeypatch):
    monkeypatch.setitem(sys.modules, "y_client", None)  # not importable: a client package without federation
    assert hooks.federation_module() is None
    off = types.ModuleType("y_client")
    off.federation = SimpleNamespace(enabled=lambda: False)
    monkeypatch.setitem(sys.modules, "y_client", off)
    assert hooks.federation_module() is None
    off.federation = on = SimpleNamespace(enabled=lambda: True)
    assert hooks.federation_module() is on


def test_a_failing_hook_leaves_the_loop_unchanged(federation, capsys):
    class Broken(FakeFederation):
        def filter_pool(self, agents):
            raise RuntimeError("server down")

        def scale_actions(self, n, user_id):
            raise RuntimeError("server down")

        def adopt_provisioned(self, client):
            raise RuntimeError("server down")

    federation(Broken())
    pool = [make_agent(1)]
    assert hooks.filter_pool(pool) is pool and hooks.scaled_round_actions(pool[0], 3) == 3
    assert hooks.adopt_provisioned(make_client(pool)) == []
    assert capsys.readouterr().err.count("Warning: federation") == 3


# --------------------------------------------------------------------------------------------- the hooks
def test_adoption_adds_the_agents_with_the_defaults_the_sampler_needs(federation):
    federation(FakeFederation(provisioned=[{"user_id": 7, "username": "n"}]))
    cl = make_client([make_agent(1)])
    added = hooks.adopt_provisioned(cl)
    assert [a.user_id for a in added] == [7] and added[0].activity_profile == "Always On"
    assert [a.user_id for a in cl.agents.agents] == [1, 7]


def test_a_client_without_the_adoption_method_is_skipped(federation):
    fed = federation(FakeFederation(provisioned=[{"user_id": 7}]))
    cl = make_client([make_agent(1)])
    del cl.adopt_federated_account
    assert hooks.adopt_provisioned(cl) == [] and "adopt_provisioned" not in fed.calls


def test_prepare_slot_rebuilds_the_hour_map_after_an_adoption_and_hides_inactive_agents(federation):
    federation(FakeFederation(hidden={2}, provisioned=[{"user_id": 7, "username": "n"}]))
    cl = make_client([make_agent(1), make_agent(2)])
    old = defaultdict(list, {0: list(cl.agents.agents)})
    rebuilt = []

    def rebuild(agents):
        rebuilt.append(list(agents))
        return defaultdict(list, {0: list(agents)})

    common, users, pool = hooks.prepare_slot(cl, list(cl.agents.agents), old, 0, rebuild)
    assert len(rebuilt) == 1 and [a.user_id for a in common] == [1, 2, 7]
    assert [a.user_id for a in users[0]] == [1, 2, 7] and [a.user_id for a in pool] == [1, 7]  # 2 is hidden


# ------------------------------------------------------------------------------------ process_agent: attention
def _run(g, cl, seed=1):
    return sampler.process_agent(g, NO_ARCHETYPES, cl, SimpleNamespace(platform_type="microblogging"), 5, None, random.Random(seed))


def test_attention_multiplier_scales_the_round_actions_of_process_agent(federation):
    fed = federation(FakeFederation(multipliers={1: 3.0, 2: 0.0}))
    cl = make_client([])
    boosted, silent, plain = make_agent(1, 3), make_agent(2, 3), make_agent(3, 3)
    assert _run(boosted, cl) == ("u1", True, None) and _run(silent, cl) == ("u2", True, None) and _run(plain, cl)[1]
    assert ("scale_actions", 3, 1) in fed.calls and ("scale_actions", 3, 2) in fed.calls
    assert 7 <= len(boosted.acted) <= 9  # 3 * 3 = 9 round actions: randint(7, 9) rounds
    assert silent.acted == []  # multiplier 0: the agent does not act in the slot (and randint(1, 0) is not drawn)
    assert 1 <= len(plain.acted) <= 3  # multiplier 1: the unscaled range


def test_process_agent_draws_the_same_with_and_without_a_unit_multiplier(federation, monkeypatch):
    off, on = make_agent(1, 5), make_agent(1, 5)
    monkeypatch.setattr(hooks, "federation_module", lambda: None)
    _run(off, make_client([]), seed=11)
    federation(FakeFederation())  # on, every multiplier 1: the same randint arguments, the same rounds
    _run(on, make_client([]), seed=11)
    assert len(off.acted) == len(on.acted) >= 3


def test_pages_are_not_scaled(federation):
    fed = federation(FakeFederation(multipliers={9: 0.0}))
    page = make_agent(9)
    page.is_page = 1
    _run(page, make_client([]))
    assert page.acted and not [c for c in fed.calls if isinstance(c, tuple)]


# -------------------------------------------------------------------------- the real run_simulation loop
@pytest.fixture
def loop(monkeypatch):
    """`process_runner.run_simulation` with the database and the app replaced: only the slot logic runs."""
    import sqlalchemy
    import sqlalchemy.orm
    import y_web

    monkeypatch.setattr(y_web, "create_app", lambda db_type: SimpleNamespace(config={"SQLALCHEMY_DATABASE_URI": "sqlite://"}))
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: SimpleNamespace(dispose=lambda: None))
    fake_session = SimpleNamespace(
        query=lambda *a, **k: SimpleNamespace(filter_by=lambda **kw: SimpleNamespace(first=lambda: None)),
        close=lambda: None, add=lambda x: None, commit=lambda: None,
    )
    monkeypatch.setattr(sqlalchemy.orm, "sessionmaker", lambda bind=None: (lambda: fake_session))
    built = []

    def users_per_hour(population, agents, session):
        built.append([a.user_id for a in agents])
        return defaultdict(list, {h: list(agents) for h in range(24)})

    monkeypatch.setattr(process_runner, "get_users_per_hour", users_per_hour)

    def run(cl):
        process_runner.run_simulation(cl, 1, "agents.json", SimpleNamespace(platform_type="other"), SimpleNamespace(id=1), "sqlite")
        return built

    return run


def test_run_simulation_hides_inactive_agents_scales_actions_and_adopts(federation, loop):
    fed = federation(FakeFederation(hidden={2}, multipliers={1: 3.0}, provisioned=[{"user_id": 7, "username": "n"}]))
    agents = [make_agent(1, 3), make_agent(2, 3), make_agent(3, 3)]
    cl = make_client(agents, slots=2)
    built = loop(cl)
    by_id = {a.user_id: a for a in cl.agents.agents}
    assert fed.calls.count("adopt_provisioned") == 2 and fed.calls.count("filter_pool") == 2  # once per slot
    assert by_id[2].acted == []  # hidden: never sampled
    assert 14 <= len(by_id[1].acted) <= 18  # 2 slots of 7..9 rounds (3 * 3 round actions)
    assert 2 <= len(by_id[7].acted) <= 6 and by_id[7].activity_profile == "Always On"  # adopted before the first slot
    assert built == [[], [1, 2, 3], [1, 2, 3, 7]]  # pages, the day, then the map rebuilt once with the new agent


def test_run_simulation_without_a_federation_samples_everybody_once_per_slot(monkeypatch, loop):
    monkeypatch.setattr(hooks, "federation_module", lambda: None)
    agents = [make_agent(i, 1) for i in (1, 2, 3)]
    cl = make_client(agents, slots=2)
    built = loop(cl)
    assert [len(a.acted) for a in cl.agents.agents] == [2, 2, 2] and built == [[], [1, 2, 3]]  # pages, then once per day, as before
