import pytest

pytestmark = pytest.mark.unit


def test_opinion_evolution_prefers_experiment_interests():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "def _resolve_opinion_evolution_topics(expid):" in source
    assert "db.session.query(Interests).all()" in source
    assert "if topics:" in source
    assert "return topics" in source
    assert "Exp_Topic.query.filter_by(exp_id=expid).all()" in source
    assert "db.session.query(Topic_List)" in source


def test_opinion_evolution_route_uses_topic_resolver():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "topics = _resolve_opinion_evolution_topics(expid)" in source


def test_opinion_evolution_resolves_actual_experiment_db():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "def _resolve_opinion_experiment_db_name(experiment):" in source
    assert 'os.path.join("experiments", uid, "simulation.db")' in source
    assert 'os.path.join("experiments", uid, "database_server.db")' in source
    assert 'return {"rounds", "agent_opinion"}.issubset(tables)' in source


def test_opinion_evolution_route_validates_bound_experiment_schema():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "opinion_db_name = _resolve_opinion_experiment_db_name(experiment)" in source
    assert "_experiment_db_has_required_opinion_tables(bound_db_uri)" in source
    assert "does not contain opinion evolution tables" in source


def test_opinion_evolution_bootstraps_missing_agent_opinions():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert (
        "def _bootstrap_initial_agent_opinions_if_missing(expid, experiment):" in source
    )
    assert "OpinionEvolutionCache.query.filter_by(exp_id=expid).delete()" in source
    assert (
        "OpinionEvolutionSampledAgents.query.filter_by(exp_id=expid).delete()" in source
    )
    assert "_bootstrap_initial_agent_opinions_if_missing(expid, experiment)" in source


def test_opinion_evolution_invalidates_stale_cache_when_db_was_reset():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "def _invalidate_stale_opinion_evolution_cache(expid):" in source
    assert (
        "cache_max_time = int(latest_cache.day) * 24 + int(latest_cache.hour)" in source
    )
    assert "db_max_time = int(max_round.day) * 24 + int(max_round.hour)" in source
    assert "_invalidate_stale_opinion_evolution_cache(expid)" in source


def test_opinion_evolution_template_exposes_max_day_and_hour():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/opinion_evolution.html",
        "r",
    ).read()

    assert "maxDay: {{ max_day }}" in source
    assert "maxHour: {{ max_hour }}" in source


def test_opinion_evolution_template_keeps_all_granularity_buttons_bound():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/opinion_evolution.html",
        "r",
    ).read()

    assert source.count('class="granularity-button"') >= 2
    assert 'data-granularity="daily"' in source
    assert 'data-granularity="weekly"' in source


def test_opinion_evolution_js_refreshes_group_trends_state():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/admin-opinion.js",
        "r",
    ).read()

    assert "_currentGroupTrendsData = data.group_trends_data;" in source
    assert (
        "_evoGroupTrendsChartInstance.data.datasets = createGroupTrendsDatasets(data.group_trends_data);"
        in source
    )
    assert "_maxTimeValue = config.maxTick ||" in source


def test_opinion_evolution_uses_agent_opinion_row_id_tie_breaker():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "Agent_Opinion.id," in source
    assert "(day, hour, tid, row_id)" in source
    assert '"row_id": row_id' in source


def test_opinion_evolution_ignores_legacy_cache_without_row_order():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_opinion.py",
        "r",
    ).read()

    assert "def _is_legacy_opinion_cache_state(cache_entry):" in source
    assert '"row_id" not in opinion_state' in source
