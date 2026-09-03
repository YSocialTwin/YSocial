"""
Patch failing tests to work with SA2 select() API.

Strategy: inject _FakeSelect / _SelectRoutingSession helpers into each test
file, then add the two monkeypatches (select + db) that each failing test
needs so that db.session.scalars(select(PatchedModel)…) routes through the
old Model.query.… stub that the test already set up.
"""
import re, textwrap

SA2_STUBS = '''
# ---------------------------------------------------------------------------
# SA2 test stubs — bypass select() ORM validation for unit-test stubs
# ---------------------------------------------------------------------------
class _FakeSelect:
    """Captures model/args without invoking SQLAlchemy ORM coercions."""
    def __init__(self, *models, **kw):
        self._models = models
        self._kw = {}
    def filter_by(self, **kw): self._kw = kw; return self
    def filter(self, *a): return self
    def select_from(self, m): return self
    def where(self, *a): return self
    def order_by(self, *a): return self
    def limit(self, n): return self

class _ScalarsResult:
    """Wraps a legacy query so .all()/.first() work uniformly."""
    def __init__(self, q): self._q = q
    def all(self):
        return self._q.all() if hasattr(self._q, 'all') else []
    def first(self):
        return self._q.first() if hasattr(self._q, 'first') else None
    def one_or_none(self):
        return self._q.one_or_none() if hasattr(self._q, 'one_or_none') else None
    def one(self):
        return self._q.one() if hasattr(self._q, 'one') else None

class _SelectRoutingSession:
    """Routes scalars(select(Model).filter_by(…)) → Model.query.filter_by(…)."""
    def __init__(self, inner=None): self._inner = inner
    def scalars(self, stmt):
        if isinstance(stmt, _FakeSelect) and stmt._models:
            model = stmt._models[0]
            q = getattr(model, 'query', None)
            if q is not None:
                if stmt._kw:
                    q = q.filter_by(**stmt._kw)
                return _ScalarsResult(q)
        return _ScalarsResult(
            type('_Empty', (), {'all': lambda s: [], 'first': lambda s: None,
                                'one_or_none': lambda s: None})()
        )
    def scalar(self, stmt): return None
    def __getattr__(self, name):
        if self._inner is not None:
            return getattr(self._inner, name)
        raise AttributeError(f'_SelectRoutingSession has no attribute {name!r}')

'''

_FAKE_SELECT_LINE = "    monkeypatch.setattr(mod, \"select\", lambda *a, **kw: _FakeSelect(*a))"
_FAKE_SELECT_LINE_HELPERS = "    monkeypatch.setattr(_helpers, \"select\", lambda *a, **kw: _FakeSelect(*a))"
_FAKE_SELECT_LINE_CRUD = "    monkeypatch.setattr(_crud, \"select\", lambda *a, **kw: _FakeSelect(*a))"


# ── helpers ──────────────────────────────────────────────────────────────────

def read(p):
    with open(p) as f: return f.read()

def write(p, s):
    with open(p, 'w') as f: f.write(s)

def insert_after(src, anchor, insertion):
    """Insert `insertion` once, right after the first occurrence of `anchor`."""
    idx = src.find(anchor)
    if idx == -1:
        raise ValueError(f"Anchor not found: {anchor!r}")
    pos = idx + len(anchor)
    return src[:pos] + insertion + src[pos:]

def append_before(src, anchor, insertion):
    """Insert `insertion` once, right before the first occurrence of `anchor`."""
    idx = src.find(anchor)
    if idx == -1:
        raise ValueError(f"Anchor not found: {anchor!r}")
    return src[:idx] + insertion + src[idx:]


# ── inject SA2 stubs block after last top-level import ───────────────────────

def inject_stubs(src):
    """Add SA2_STUBS block before the first 'def test_' or 'class Test' line."""
    m = re.search(r'^(def test_|class Test)', src, re.MULTILINE)
    if not m:
        raise ValueError("Cannot find first test function/class")
    return src[:m.start()] + SA2_STUBS + src[m.start():]


# ── per-file patches ─────────────────────────────────────────────────────────

BASE = "/sessions/rcw-01wctwebefnqcvjjaxw42yan/mnt/YWeb/y_web/tests"

# ════════════════════════════════════════════════════════════════════════════
# 1.  test_experiment_server_status_lifecycle.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_experiment_server_status_lifecycle.py"
src = read(p)
src = inject_stubs(src)

# start_experiment test: change db setattr + add select patch
src = src.replace(
    '    monkeypatch.setattr(mod, "db", SimpleNamespace(session=fake_session))\n'
    '    monkeypatch.setattr(\n'
    '        mod,\n'
    '        "Exps",\n'
    '        SimpleNamespace(query=fake_session, running="running", exp_status="exp_status"),\n'
    '    )\n'
    '\n'
    '    result = mod.start_experiment.__wrapped__(1)',
    '    monkeypatch.setattr(mod, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(mod, "db", SimpleNamespace(session=_SelectRoutingSession(fake_session)))\n'
    '    monkeypatch.setattr(\n'
    '        mod,\n'
    '        "Exps",\n'
    '        SimpleNamespace(query=fake_session, running="running", exp_status="exp_status"),\n'
    '    )\n'
    '\n'
    '    result = mod.start_experiment.__wrapped__(1)',
    1,
)

# stop_experiment test: change db setattr + add select patch
src = src.replace(
    '    monkeypatch.setattr(mod, "db", SimpleNamespace(session=fake_session))\n'
    '    monkeypatch.setattr(\n'
    '        mod,\n'
    '        "Exps",\n'
    '        SimpleNamespace(query=fake_session, running="running", exp_status="exp_status"),\n'
    '    )\n'
    '    monkeypatch.setattr(mod, "Client", SimpleNamespace(query=fake_session))',
    '    monkeypatch.setattr(mod, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(mod, "db", SimpleNamespace(session=_SelectRoutingSession(fake_session)))\n'
    '    monkeypatch.setattr(\n'
    '        mod,\n'
    '        "Exps",\n'
    '        SimpleNamespace(query=fake_session, running="running", exp_status="exp_status"),\n'
    '    )\n'
    '    monkeypatch.setattr(mod, "Client", SimpleNamespace(query=fake_session))',
    1,
)

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 2.  test_adhoc_client_shutdown.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_adhoc_client_shutdown.py"
src = read(p)
src = inject_stubs(src)

# Add select + db patches before the failing call
src = src.replace(
    '    monkeypatch.setattr(mod, "Exps", SimpleNamespace(query=_FakeExpsQuery()))\n'
    '    monkeypatch.setattr(mod, "experiment_details", lambda uid: f"details:{uid}")',
    '    monkeypatch.setattr(mod, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(mod, "db", SimpleNamespace(session=_SelectRoutingSession()))\n'
    '    monkeypatch.setattr(mod, "Exps", SimpleNamespace(query=_FakeExpsQuery()))\n'
    '    monkeypatch.setattr(mod, "experiment_details", lambda uid: f"details:{uid}")',
    1,
)

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 3.  test_social_follow_helpers.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_social_follow_helpers.py"
src = read(p)
src = inject_stubs(src)

# Add select + db patches before the call that fails
src = src.replace(
    '    monkeypatch.setattr(\n'
    '        users_module,\n'
    '        "Page",\n'
    '        SimpleNamespace(\n'
    '            query=SimpleNamespace(\n'
    '                filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)\n'
    '            )\n'
    '        ),\n'
    '    )\n'
    '\n'
    '    followers, followees',
    '    monkeypatch.setattr(\n'
    '        users_module,\n'
    '        "Page",\n'
    '        SimpleNamespace(\n'
    '            query=SimpleNamespace(\n'
    '                filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)\n'
    '            )\n'
    '        ),\n'
    '    )\n'
    '    monkeypatch.setattr(users_module, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(users_module, "db", SimpleNamespace(session=_SelectRoutingSession()))\n'
    '\n'
    '    followers, followees',
    1,
)

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 4.  test_memory_enabled_detection.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_memory_enabled_detection.py"
src = read(p)
src = inject_stubs(src)

# Patch _call_experiment_memory_enabled to also stub select + db
old_call = (
    '    with patch("y_web.routes.social.helpers.Exps") as mock_exps:\n'
    '        mock_exps.query.filter_by.return_value.first.return_value = mock_exp\n'
    '        with patch(\n'
    '            "y_web.routes.social.helpers.get_writable_path",\n'
    '            return_value=writable_base,\n'
    '        ):\n'
    '            return _experiment_memory_enabled(1)'
)
new_call = (
    '    with patch("y_web.routes.social.helpers.Exps") as mock_exps, \\\n'
    '         patch("y_web.routes.social.helpers.select",\n'
    '               side_effect=lambda *a, **kw: _FakeSelect(*a)) as _sel, \\\n'
    '         patch("y_web.routes.social.helpers.db",\n'
    '               new=SimpleNamespace(session=_SelectRoutingSession())), \\\n'
    '         patch("y_web.routes.social.helpers.get_writable_path",\n'
    '               return_value=writable_base):\n'
    '        mock_exps.query.filter_by.return_value.first.return_value = mock_exp\n'
    '        return _experiment_memory_enabled(1)'
)
src = src.replace(old_call, new_call, 1)

# Add SimpleNamespace import if not already present
if 'from types import SimpleNamespace' not in src:
    src = src.replace('import pytest\n', 'import pytest\nfrom types import SimpleNamespace\n', 1)

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 5.  test_bulk_population_insert.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_bulk_population_insert.py"
src = read(p)
src = inject_stubs(src)

# Both failing tests have identical structure: add select patch + configure scalars routing
# Patch 1 (test_generate_population_uses_bulk_insert):
old_patch1 = (
    '        patch("y_web.src.agents.population.Population") as mock_population_cls,\n'
    '        patch(\n'
    '            "y_web.src.agents.population.PopulationActivityProfile"\n'
    '        ) as mock_profile_cls,\n'
    '        patch("y_web.src.agents.population.db") as mock_db,\n'
    '        patch("y_web.src.agents.population.AgeClass") as mock_age_class,\n'
    '        patch("y_web.src.agents.population.Toxicity_Levels") as mock_toxicity,\n'
    '        patch("y_web.src.agents.population.Leanings") as mock_leanings,\n'
    '        patch("y_web.src.agents.population.Profession") as mock_profession,\n'
    '        patch("y_web.src.agents.population.Education") as mock_education,\n'
    '    ):\n'
    '        mock_session = mock_db.session\n'
    '\n'
    '        # Setup mocks\n'
    '        mock_population_cls.query.filter_by.return_value.first.return_value = (\n'
    '            mock_population\n'
    '        )\n'
    '        mock_profile_cls.query.filter_by.return_value.all.return_value = []'
)
new_patch1 = (
    '        patch("y_web.src.agents.population.Population") as mock_population_cls,\n'
    '        patch(\n'
    '            "y_web.src.agents.population.PopulationActivityProfile"\n'
    '        ) as mock_profile_cls,\n'
    '        patch("y_web.src.agents.population.db") as mock_db,\n'
    '        patch("y_web.src.agents.population.select",\n'
    '              side_effect=lambda *a, **kw: _FakeSelect(*a)),\n'
    '        patch("y_web.src.agents.population.AgeClass") as mock_age_class,\n'
    '        patch("y_web.src.agents.population.Toxicity_Levels") as mock_toxicity,\n'
    '        patch("y_web.src.agents.population.Leanings") as mock_leanings,\n'
    '        patch("y_web.src.agents.population.Profession") as mock_profession,\n'
    '        patch("y_web.src.agents.population.Education") as mock_education,\n'
    '    ):\n'
    '        mock_session = mock_db.session\n'
    '        mock_session.scalars.side_effect = _SelectRoutingSession().scalars\n'
    '\n'
    '        # Setup mocks\n'
    '        mock_population_cls.query.filter_by.return_value.first.return_value = (\n'
    '            mock_population\n'
    '        )\n'
    '        mock_profile_cls.query.filter_by.return_value.all.return_value = []'
)
src = src.replace(old_patch1, new_patch1, 1)

# Patch 2 (test_bulk_insert_preserves_agent_count) – same structure
src = src.replace(old_patch1, new_patch1, 1)

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 6.  test_hpc_progress_tracking.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_hpc_progress_tracking.py"
src = read(p)
src = inject_stubs(src)

# For each of the 3 start_hpc_client tests that set Client_Execution and commit:
# add select patch + scalars routing
#
# Common pattern near end of setup in all 3 failing tests:
#   monkeypatch.setattr("y_web.src.hpc.client.db.session.commit", lambda: None)
#   class _FakeClientExecution: ...
#   _FakeClientExecution.query... = ...
#   monkeypatch.setattr("y_web.src.hpc.client.Client_Execution", _FakeClientExecution)
#
# We insert select + scalars patches after the commit patch.

def add_hpc_select_patch(src, commit_anchor, extra_after_commit=""):
    """Insert select+scalars patches after the db.session.commit monkeypatch."""
    injection = (
        '    monkeypatch.setattr("y_web.src.hpc.client.select",\n'
        '                        lambda *a, **kw: _FakeSelect(*a))\n'
        '    import y_web.src.hpc.client as _hpc_mod\n'
        '    monkeypatch.setattr(_hpc_mod.db.session, "scalars",\n'
        '                        _SelectRoutingSession().scalars)\n'
    )
    return src.replace(commit_anchor, commit_anchor + '\n' + injection, 1)

# test_start_hpc_client_clears_stale_recycled_pid_and_restarts
src = add_hpc_select_patch(
    src,
    '    monkeypatch.setattr("y_web.src.hpc.client.db.session.commit", lambda: None)\n'
    '\n'
    '    class _FakeClientExecution:\n'
    '        query = MagicMock()\n'
    '\n'
    '    _FakeClientExecution.query.filter_by.return_value = existing_exec_q\n'
    '    monkeypatch.setattr("y_web.src.hpc.client.Client_Execution", _FakeClientExecution)\n'
    '\n'
    '    process = start_hpc_client(mock_exp, mock_cli, mock_population)\n'
    '\n'
    '    assert process.pid == 88888\n'
    '    assert mock_cli.pid == 88888',
)

# test_start_hpc_client_syncs_duration_from_matrix_config (find its commit+CE block)
SYNCS_ANCHOR = (
    '    monkeypatch.setattr("y_web.src.hpc.client.db.session.commit", lambda: None)\n'
    '\n'
    '    class _FakeClientExecution:\n'
    '        query = MagicMock()\n'
    '\n'
    '    _FakeClientExecution.query.filter_by.return_value.first.return_value = None\n'
    '    monkeypatch.setattr("y_web.src.hpc.client.Client_Execution", _FakeClientExecution)\n'
    '    monkeypatch.setattr(\n'
    '        "y_web.src.hpc.client.db.session.add", lambda obj: added_objects.append(obj)\n'
    '    )\n'
    '\n'
    '    process = start_hpc_client(mock_exp, mock_cli, mock_population)'
)

injection_syncs = (
    '    monkeypatch.setattr("y_web.src.hpc.client.select",\n'
    '                        lambda *a, **kw: _FakeSelect(*a))\n'
    '    import y_web.src.hpc.client as _hpc_mod\n'
    '    monkeypatch.setattr(_hpc_mod.db.session, "scalars",\n'
    '                        _SelectRoutingSession().scalars)\n'
)
src = src.replace(SYNCS_ANCHOR, SYNCS_ANCHOR[:SYNCS_ANCHOR.find('\n    class _FakeClientExecution')] + '\n' + injection_syncs + SYNCS_ANCHOR[SYNCS_ANCHOR.find('\n    class _FakeClientExecution'):], 1)

# test_start_hpc_client_photo_sharing_uses_top_level_hpc_layout (same structure)
PHOTO_ANCHOR = (
    '    monkeypatch.setattr("y_web.src.hpc.client.db.session.commit", lambda: None)\n'
    '\n'
    '    class _FakeClientExecution:\n'
    '        query = MagicMock()\n'
    '\n'
    '        def __init__(self, **kwargs):\n'
    '            for key, value in kwargs.items():\n'
    '                setattr(self, key, value)\n'
    '\n'
    '    _FakeClientExecution.query.filter_by.return_value.first.return_value = None\n'
    '    monkeypatch.setattr("y_web.src.hpc.client.Client_Execution", _FakeClientExecution)\n'
    '    added_objects = []\n'
    '    monkeypatch.setattr(\n'
    '        "y_web.src.hpc.client.db.session.add", lambda obj: added_objects.append(obj)\n'
    '    )\n'
    '\n'
    '    process = start_hpc_client(mock_exp, mock_cli, mock_population)'
)
src = src.replace(
    PHOTO_ANCHOR,
    PHOTO_ANCHOR[:PHOTO_ANCHOR.find('\n    class _FakeClientExecution')] + '\n' + injection_syncs + PHOTO_ANCHOR[PHOTO_ANCHOR.find('\n    class _FakeClientExecution'):],
    1,
)

# test_admin_progress_refreshes_hpc_client_log_when_stale
# Uses patch() context manager style – add select + db patches
ADMIN_OLD = (
    '        patch("y_web.routes.admin.sub.clients._details.Client") as client_model,\n'
    '        patch(\n'
    '            "y_web.routes.admin.sub.clients._details.Client_Execution"\n'
    '        ) as execution_model,\n'
    '        patch("y_web.routes.admin.sub.clients._details.Exps") as exp_model,'
)
ADMIN_NEW = (
    '        patch("y_web.routes.admin.sub.clients._details.select",\n'
    '              side_effect=lambda *a, **kw: _FakeSelect(*a)),\n'
    '        patch("y_web.routes.admin.sub.clients._details.db",\n'
    '              new=SimpleNamespace(session=_SelectRoutingSession())),\n'
    '        patch("y_web.routes.admin.sub.clients._details.Client") as client_model,\n'
    '        patch(\n'
    '            "y_web.routes.admin.sub.clients._details.Client_Execution"\n'
    '        ) as execution_model,\n'
    '        patch("y_web.routes.admin.sub.clients._details.Exps") as exp_model,'
)
src = src.replace(ADMIN_OLD, ADMIN_NEW, 1)

# Need SimpleNamespace for the admin test
if 'from types import SimpleNamespace' not in src:
    src = src.replace('import pytest\n', 'import pytest\nfrom types import SimpleNamespace\n', 1)

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 7.  test_microblog_chat_component.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_microblog_chat_component.py"
src = read(p)
src = inject_stubs(src)

# test_follow_round_resolution_preserves_photo_round_strings:
# add select + db patches before the assert
OLD_FOLLOW = (
    '    monkeypatch.setattr(models, "Exps", FakeExps)\n'
    '    monkeypatch.setattr(\n'
    '        common,\n'
    '        "open_experiment_session",\n'
    '        lambda exp: (FakeSession(), FakeEngine()),\n'
    '    )\n'
    '\n'
    '    assert common._resolve_follow_round_id(9) == "round-abc"'
)
NEW_FOLLOW = (
    '    monkeypatch.setattr(models, "Exps", FakeExps)\n'
    '    monkeypatch.setattr(\n'
    '        common,\n'
    '        "open_experiment_session",\n'
    '        lambda exp: (FakeSession(), FakeEngine()),\n'
    '    )\n'
    '    monkeypatch.setattr(common, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(common, "db", SimpleNamespace(session=_SelectRoutingSession()))\n'
    '\n'
    '    assert common._resolve_follow_round_id(9) == "round-abc"'
)
src = src.replace(OLD_FOLLOW, NEW_FOLLOW, 1)

# test_photo_chat_contacts_follow_the_photo_follow_graph: add `from y_web import db`
OLD_PHOTO_INT = '    app = create_app()\n    with app.app_context():\n        exp = db.session.scalars'
NEW_PHOTO_INT = '    from y_web import db\n    app = create_app()\n    with app.app_context():\n        exp = db.session.scalars'
src = src.replace(OLD_PHOTO_INT, NEW_PHOTO_INT, 1)

# Need SimpleNamespace import
if 'from types import SimpleNamespace' not in src:
    src = src.replace(
        'from pathlib import Path\nfrom types import SimpleNamespace',
        'from pathlib import Path\nfrom types import SimpleNamespace',
    )

write(p, src)
print(f"✓ {p}")


# ════════════════════════════════════════════════════════════════════════════
# 8.  test_copy_experiment.py
# ════════════════════════════════════════════════════════════════════════════
p = f"{BASE}/test_copy_experiment.py"
src = read(p)
src = inject_stubs(src)

# --- get_suggested_port tests: add _helpers.select + _helpers.db patches ---
# Each test ends with:  monkeypatch.setattr(_helpers, "Exps", ...)  [then is_port_free]
# We add select+db right after the last _helpers.setattr before the assert.

def patch_get_suggested_port_test(src, exps_setattr_line, assert_line):
    """Add select+db patches between the Exps setattr and the assert."""
    anchor = exps_setattr_line + '\n\n' + assert_line
    replacement = (
        exps_setattr_line + '\n'
        '    monkeypatch.setattr(_helpers, "select", lambda *a, **kw: _FakeSelect(*a))\n'
        '    monkeypatch.setattr(_helpers, "db", SimpleNamespace(session=_SelectRoutingSession()))\n'
        '\n' + assert_line
    )
    return src.replace(anchor, replacement, 1)

# test 1
src = patch_get_suggested_port_test(
    src,
    '    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 5000)',
    '    assert _helpers.get_suggested_port() == 5000',
)

# test 2 – has Client + Client_Execution patches before is_port_free
src = patch_get_suggested_port_test(
    src,
    '    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 5003)',
    '    assert _helpers.get_suggested_port() == 5003',
)

# test 3 – legacy stopped
src = patch_get_suggested_port_test(
    src,
    '    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 5000)',
    '    assert _helpers.get_suggested_port() == 5000',
)

# test 4 – scans past 6000
src = patch_get_suggested_port_test(
    src,
    '    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 6001)',
    '    assert _helpers.get_suggested_port() == 6001',
)

# test 5 – falls back to OS port
src = patch_get_suggested_port_test(
    src,
    '    monkeypatch.setattr(_helpers.socket, "socket", lambda *args, **kwargs: FakeSocket())',
    '    assert _helpers.get_suggested_port() == 61000',
)

# --- copy_experiment_group tests: add _crud.select + _crud.db patches ---
# Both tests call `_crud._copy_experiment_group(...)`.
# In test `test_copy_experiment_group_builds_one_copy_per_source_experiment`:
OLD_CG1 = (
    '    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())\n'
    '    monkeypatch.setattr(\n'
    '        _crud, "get_visible_experiment_query", lambda user: FakeVisibleQuery()\n'
    '    )\n'
    '    monkeypatch.setattr(_crud, "Exps", FakeExps)\n'
    '    monkeypatch.setattr(\n'
    '        _crud,\n'
    '        "_create_single_experiment_copy",\n'
    '        lambda source_exp, new_name, exp_group: created_calls.append('
)
NEW_CG1 = (
    '    monkeypatch.setattr(_crud, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(_crud, "db", SimpleNamespace(session=_SelectRoutingSession()))\n'
    '    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())\n'
    '    monkeypatch.setattr(\n'
    '        _crud, "get_visible_experiment_query", lambda user: FakeVisibleQuery()\n'
    '    )\n'
    '    monkeypatch.setattr(_crud, "Exps", FakeExps)\n'
    '    monkeypatch.setattr(\n'
    '        _crud,\n'
    '        "_create_single_experiment_copy",\n'
    '        lambda source_exp, new_name, exp_group: created_calls.append('
)
src = src.replace(OLD_CG1, NEW_CG1, 1)

# test_copy_experiment_group_reports_partial_failure
OLD_CG2 = (
    '    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())\n'
    '    monkeypatch.setattr(\n'
    '        _crud, "get_visible_experiment_query", lambda user: FakeVisibleQuery()\n'
    '    )\n'
    '    monkeypatch.setattr(_crud, "Exps", FakeExps)\n'
    '    monkeypatch.setattr(\n'
    '        _crud,\n'
    '        "_create_single_experiment_copy",\n'
    '        lambda source_exp, new_name, exp_group: source_exp.idexp == 10,\n'
    '    )'
)
NEW_CG2 = (
    '    monkeypatch.setattr(_crud, "select", lambda *a, **kw: _FakeSelect(*a))\n'
    '    monkeypatch.setattr(_crud, "db", SimpleNamespace(session=_SelectRoutingSession()))\n'
    '    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())\n'
    '    monkeypatch.setattr(\n'
    '        _crud, "get_visible_experiment_query", lambda user: FakeVisibleQuery()\n'
    '    )\n'
    '    monkeypatch.setattr(_crud, "Exps", FakeExps)\n'
    '    monkeypatch.setattr(\n'
    '        _crud,\n'
    '        "_create_single_experiment_copy",\n'
    '        lambda source_exp, new_name, exp_group: source_exp.idexp == 10,\n'
    '    )'
)
src = src.replace(OLD_CG2, NEW_CG2, 1)

write(p, src)
print(f"✓ {p}")

print("\nAll patches applied.")
