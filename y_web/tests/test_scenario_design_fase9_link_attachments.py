"""Integration test: Fase 9 follow-up -- "link a una pagina news/immagine
nel composer", scoped to Scenario Design's own draft/editor composer only
(never the live YWeb composer or hpc/standard "runtimes" themselves, see
docs/decisions.md for the explicit scope confirmation and the two design
decisions this feature was built against: (a) one news-sentinel Website
row per *scenario*, reused across every news-link post in that scenario;
(b) the admin can edit the auto-fetched title/summary by hand afterwards,
via the same PUT endpoint used for every other post field).

Covers, end to end on a real ``create_app()`` boot:

* ``POST .../posts/<tmp_id>/link_preview`` -- success for both
  ``link_kind`` values, writing ``link_url``/``link_kind``/``link_title``/
  ``link_summary`` onto the draft post; ``LinkPreviewError`` -> 502 with
  its own machine-readable code; ``invalid_link_kind``/``missing_field``
  -> 400.
* ``PUT .../posts/<tmp_id>`` -- setting link fields directly (the "admin
  edits the fetched title/summary by hand" path), an invalid
  ``link_kind`` -> 400, and clearing ``link_url`` clearing the whole
  attachment (``link_kind``/``link_title``/``link_summary`` all reset).
* Real publish materialization for **Standard** (``adapters/standard.py``):
  a news-link post materializes a real ``Articles`` row (correct
  ``title``/``summary``/``link``) and a real ``Post.news_id``; an
  image-link post materializes a real ``Images`` row and
  ``Post.image_id``; two news-link posts in the *same* scenario reuse the
  *same* sentinel ``Websites`` row (never a second one); a link URL
  longer than Standard's ``Images.url``/``Articles.link`` column
  (VARCHAR(200)) is rejected with ``link_url_too_long`` (422) rather than
  silently truncated or crashing the publish transaction.
* Real publish materialization for **HPC** (``adapters/hpc.py``): same
  assertions against the real UUID-keyed physical schema -- a long URL is
  *not* rejected here, since HPC's ``Article.link``/``Image.url`` are
  unbounded ``Text`` columns (YSimulator's own schema, no equivalent
  constraint to Standard's).

Same sandbox sqlite-write limitation as every other integration test in
this module (ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x/§F6.10/
§F7.7): every test here needs a real per-experiment sqlite file and skips
cleanly via ``_can_actually_write_sqlite_files()`` in this environment.

Piano di implementazione, Fase 9 follow-up ("link nel composer").
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import registry


def _suite_is_installed():
    return registry.runtime_spec("scenario_design").path.exists()


def _ysimulator_is_installed():
    import os

    from y_web.src.system.path_utils import get_base_path

    return os.path.isdir(
        os.path.join(get_base_path(), "external", "YSimulator", "YSimulator")
    )


def _can_actually_write_sqlite_files() -> bool:
    import os
    import uuid

    from y_web.src.system.path_utils import get_writable_path

    probe_dir = get_writable_path(
        os.path.join("y_web", "experiments", f"_probe_fase9_link_{uuid.uuid4().hex}")
    )
    try:
        os.makedirs(probe_dir, exist_ok=True)
        db_path = os.path.join(probe_dir, "probe.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def _make_exp(app, name="sd-fase9-link-exp"):
    import os

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder = get_writable_path(os.path.join("y_web", "experiments", name))
    os.makedirs(folder, exist_ok=True)

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            exp_name=name,
            db_name=f"experiments/{name}/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


def _make_hpc_exp(app, name="sd-fase9-link-hpc-exp"):
    """Same helper as test_scenario_design_fase7_publish_hpc.py's
    ``_make_hpc_exp`` -- an ``Exps`` row with ``simulator_type="HPC"``,
    its physical sqlite file seeded with YSimulator's real schema at the
    same path ``resolve_experiment_db_path`` will later resolve."""
    import os

    from sqlalchemy import create_engine

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder = get_writable_path(os.path.join("y_web", "experiments", name))
    os.makedirs(folder, exist_ok=True)
    db_path = os.path.join(folder, "database_server.db")

    from YSimulator.YServer.classes.models import Base as HpcBase

    engine = create_engine(f"sqlite:///{db_path}")
    HpcBase.metadata.create_all(engine)
    engine.dispose()

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            simulator_type="HPC",
            exp_name=name,
            db_name=f"experiments/{name}/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


def _seed_hpc_author(app, exp_id, *, username="hpc_link_author"):
    import uuid

    from modules.scenario_editor.backend.hpc_session import hpc_session
    from YSimulator.YServer.classes.models import User_mgmt as HpcUser

    from y_web.src.models import Exps

    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        user_id = str(uuid.uuid4())
        with hpc_session(exp) as hsession:
            hsession.add(HpcUser(id=user_id, username=username))
            hsession.commit()
        return user_id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


pytestmark = pytest.mark.integration


@pytest.fixture
def sd_app():
    if not _suite_is_installed():
        pytest.skip("ScenarioDesign suite not checked out in this environment")
    if not _can_actually_write_sqlite_files():
        pytest.skip(
            "Sandbox cannot commit new sqlite files under this repo's "
            "y_web/experiments/ subtree in this environment (known "
            "limitation, ScenarioDesign/docs/decisions.md §F1.4/§F1.5/"
            "§F3.x/§F6.10/§F7.7) -- re-run in a real dev environment to "
            "exercise this module."
        )

    from y_web import create_app

    boot_app = create_app(db_type="sqlite")
    boot_app.config["TESTING"] = True
    boot_app.config["WTF_CSRF_ENABLED"] = False
    return boot_app


@pytest.fixture
def sd_client(sd_app):
    from y_web.src.models import User_mgmt

    client = sd_app.test_client()
    with sd_app.app_context():
        test_user = User_mgmt(
            username="fase9_link_author",
            email="fase9_link_author@test.com",
            password=generate_password_hash("test123"),
            joined_on=1234567890,
        )
        db.session.add(test_user)
        db.session.commit()
        user_id = test_user.id
    _login(client, user_id)
    return client, user_id


def _create_scenario(client, exp_id, name="S1"):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios",
        json={"name": name},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["scenario"]["id"]


def _create_thread(client, exp_id, scenario_id, tmp_id="t1"):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": tmp_id},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["thread"]["id"]


def _add_post(
    client,
    exp_id,
    scenario_id,
    thread_id,
    *,
    tmp_id,
    parent_tmp_id,
    author_user_id,
    content="",
):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={
            "tmp_id": tmp_id,
            "parent_tmp_id": parent_tmp_id,
            "author_user_id": author_user_id,
            "content": content,
        },
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["post"]["id"]


def _publish(client, exp_id, scenario_id, *, idempotency_key=None):
    headers = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json={},
        headers=headers,
    )


def _put_post(client, exp_id, scenario_id, tmp_id, payload):
    return client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/posts/{tmp_id}",
        json=payload,
    )


def _link_preview(client, exp_id, scenario_id, tmp_id, payload):
    return client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/posts/{tmp_id}/link_preview",
        json=payload,
    )


# ---------------------------------------------------------------------------
# link_preview endpoint
# ---------------------------------------------------------------------------


def test_link_preview_endpoint_fetches_and_stores_news_preview(
    sd_app, sd_client, monkeypatch
):
    import modules.scenario_editor.backend.link_preview as link_preview_module

    def _fake_fetch(url, link_kind, **kwargs):
        assert url == "http://example.com/some-article"
        assert link_kind == "news"
        return {"title": "A real headline", "summary": "A real summary."}

    monkeypatch.setattr(link_preview_module, "fetch_link_preview", _fake_fetch)

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-news-preview")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )

    resp = _link_preview(
        client,
        exp_id,
        scenario_id,
        "root",
        {"link_url": "http://example.com/some-article", "link_kind": "news"},
    )
    assert resp.status_code == 200, resp.data
    post = resp.get_json()["post"]
    assert post["link_url"] == "http://example.com/some-article"
    assert post["link_kind"] == "news"
    assert post["link_title"] == "A real headline"
    assert post["link_summary"] == "A real summary."


def test_link_preview_endpoint_fetches_image_preview_with_empty_title_summary(
    sd_app, sd_client, monkeypatch
):
    import modules.scenario_editor.backend.link_preview as link_preview_module

    def _fake_fetch(url, link_kind, **kwargs):
        assert link_kind == "image"
        return {"title": "", "summary": ""}

    monkeypatch.setattr(link_preview_module, "fetch_link_preview", _fake_fetch)

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-image-preview")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )

    resp = _link_preview(
        client,
        exp_id,
        scenario_id,
        "root",
        {"link_url": "http://example.com/photo.jpg", "link_kind": "image"},
    )
    assert resp.status_code == 200, resp.data
    post = resp.get_json()["post"]
    assert post["link_kind"] == "image"
    assert post["link_title"] == ""
    assert post["link_summary"] == ""


def test_link_preview_endpoint_maps_fetch_error_to_502_with_its_code(
    sd_app, sd_client, monkeypatch
):
    import modules.scenario_editor.backend.link_preview as link_preview_module

    def _fake_fetch(url, link_kind, **kwargs):
        raise link_preview_module.LinkPreviewError("host_not_allowed", "nope")

    monkeypatch.setattr(link_preview_module, "fetch_link_preview", _fake_fetch)

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-fetch-error")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )

    resp = _link_preview(
        client,
        exp_id,
        scenario_id,
        "root",
        {"link_url": "http://127.0.0.1/", "link_kind": "news"},
    )
    assert resp.status_code == 502, resp.data
    assert resp.get_json()["error"]["code"] == "host_not_allowed"


def test_link_preview_endpoint_rejects_invalid_link_kind_and_missing_url(
    sd_app, sd_client
):
    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-bad-input")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )

    resp = _link_preview(
        client,
        exp_id,
        scenario_id,
        "root",
        {"link_url": "http://example.com/x", "link_kind": "video"},
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["error"]["code"] == "invalid_link_kind"

    resp = _link_preview(client, exp_id, scenario_id, "root", {"link_kind": "news"})
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["error"]["code"] == "missing_field"


# ---------------------------------------------------------------------------
# PUT: admin edits fields by hand / clears the attachment
# ---------------------------------------------------------------------------


def test_put_sets_link_fields_directly_without_fetching(sd_app, sd_client):
    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-put-set")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )

    resp = _put_post(
        client,
        exp_id,
        scenario_id,
        "root",
        {
            "link_url": "http://example.com/article",
            "link_kind": "news",
            "link_title": "Hand-written title",
            "link_summary": "Hand-written summary",
        },
    )
    assert resp.status_code == 200, resp.data
    post = resp.get_json()["post"]
    assert post["link_url"] == "http://example.com/article"
    assert post["link_kind"] == "news"
    assert post["link_title"] == "Hand-written title"
    assert post["link_summary"] == "Hand-written summary"


def test_put_admin_overrides_fetched_title_and_summary_by_hand(
    sd_app, sd_client, monkeypatch
):
    """Decision (b): the admin can edit the auto-fetched title/summary
    afterwards -- fetch via link_preview, then PUT a correction, and
    confirm the PUT value wins (never silently re-overwritten)."""
    import modules.scenario_editor.backend.link_preview as link_preview_module

    monkeypatch.setattr(
        link_preview_module,
        "fetch_link_preview",
        lambda url, link_kind, **kwargs: {
            "title": "Auto title",
            "summary": "Auto summary",
        },
    )

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-put-override")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )
    _link_preview(
        client,
        exp_id,
        scenario_id,
        "root",
        {"link_url": "http://example.com/article", "link_kind": "news"},
    )

    resp = _put_post(
        client, exp_id, scenario_id, "root", {"link_title": "Admin's own title"}
    )
    assert resp.status_code == 200, resp.data
    post = resp.get_json()["post"]
    assert post["link_title"] == "Admin's own title"
    assert post["link_summary"] == "Auto summary"  # untouched field survives


def test_put_rejects_invalid_link_kind(sd_app, sd_client):
    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-put-bad-kind")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )

    resp = _put_post(client, exp_id, scenario_id, "root", {"link_kind": "pdf"})
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["error"]["code"] == "invalid_link_kind"


def test_put_clearing_link_url_clears_the_whole_attachment(sd_app, sd_client):
    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-put-clear")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )
    _put_post(
        client,
        exp_id,
        scenario_id,
        "root",
        {
            "link_url": "http://example.com/article",
            "link_kind": "news",
            "link_title": "T",
            "link_summary": "S",
        },
    )

    resp = _put_post(client, exp_id, scenario_id, "root", {"link_url": ""})
    assert resp.status_code == 200, resp.data
    post = resp.get_json()["post"]
    assert post["link_url"] is None
    assert post["link_kind"] is None
    assert post["link_title"] is None
    assert post["link_summary"] is None


# ---------------------------------------------------------------------------
# Standard materialization
# ---------------------------------------------------------------------------


def test_standard_publish_materializes_news_link_as_real_article_and_sentinel_website(
    sd_app, sd_client
):
    from y_web.src.models import Articles, Post, Websites

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-standard-news")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    root_tmp = "root"
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id=root_tmp,
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )
    _put_post(
        client,
        exp_id,
        scenario_id,
        root_tmp,
        {
            "link_url": "http://example.com/breaking-news",
            "link_kind": "news",
            "link_title": "Breaking News Headline",
            "link_summary": "Something happened.",
        },
    )

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 201, resp.data
    real_id = resp.get_json()["id_mapping"][root_tmp]

    with sd_app.app_context():
        post = db.session.get(Post, real_id)
        assert post.news_id is not None
        assert post.image_id is None
        article = db.session.get(Articles, post.news_id)
        assert article.title == "Breaking News Headline"
        assert article.summary == "Something happened."
        assert article.link == "http://example.com/breaking-news"
        website = db.session.get(Websites, article.website_id)
        assert website.category == "scenario_design_link"
        assert f"#{scenario_id}" in website.name


def test_standard_publish_materializes_image_link_as_real_image_row(sd_app, sd_client):
    from y_web.src.models import Images, Post

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-standard-image")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    root_tmp = "root"
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id=root_tmp,
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )
    _put_post(
        client,
        exp_id,
        scenario_id,
        root_tmp,
        {
            "link_url": "http://example.com/photo.jpg",
            "link_kind": "image",
            "link_summary": "A nice photo.",
        },
    )

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 201, resp.data
    real_id = resp.get_json()["id_mapping"][root_tmp]

    with sd_app.app_context():
        post = db.session.get(Post, real_id)
        assert post.image_id is not None
        assert post.news_id is None
        image = db.session.get(Images, post.image_id)
        assert image.url == "http://example.com/photo.jpg"
        assert image.description == "A nice photo."


def test_standard_publish_reuses_the_same_sentinel_website_across_posts_in_one_scenario(
    sd_app, sd_client
):
    from y_web.src.models import Articles, Post

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-standard-sentinel-reuse")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="p1",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="p1",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="p2",
        parent_tmp_id="p1",
        author_user_id=user_id,
        content="p2",
    )
    for tmp_id, url in (
        ("p1", "http://example.com/article-one"),
        ("p2", "http://example.com/article-two"),
    ):
        _put_post(
            client,
            exp_id,
            scenario_id,
            tmp_id,
            {
                "link_url": url,
                "link_kind": "news",
                "link_title": "T",
                "link_summary": "S",
            },
        )

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 201, resp.data
    id_mapping = resp.get_json()["id_mapping"]

    with sd_app.app_context():
        post1 = db.session.get(Post, id_mapping["p1"])
        post2 = db.session.get(Post, id_mapping["p2"])
        article1 = db.session.get(Articles, post1.news_id)
        article2 = db.session.get(Articles, post2.news_id)
        assert article1.website_id == article2.website_id  # same sentinel, not two


def test_standard_publish_rejects_link_url_too_long_for_standards_schema(
    sd_app, sd_client
):
    """Images.url/Articles.link are VARCHAR(200) in Standard's own
    schema (unlike HPC's unbounded Text columns) -- a URL over that
    length must be rejected at materialization time (422,
    ``link_url_too_long``), never silently truncated into a broken
    link/image and never crashing the publish transaction with a raw
    DB error."""
    from modules.scenario_editor.backend.models import ScenarioDesignPublication

    from y_web.src.models import Post

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase9-link-standard-too-long")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=user_id,
        content="root",
    )
    long_url = "http://example.com/" + ("x" * 250)
    assert len(long_url) > 200
    _put_post(
        client,
        exp_id,
        scenario_id,
        "root",
        {
            "link_url": long_url,
            "link_kind": "news",
            "link_title": "T",
            "link_summary": "S",
        },
    )

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 422, resp.data
    assert resp.get_json()["error"]["code"] == "link_url_too_long"

    with sd_app.app_context():
        assert db.session.query(Post).count() == 0  # fully rolled back
        assert db.session.query(ScenarioDesignPublication).count() == 0 or all(
            p.status != "succeeded"
            for p in db.session.query(ScenarioDesignPublication).all()
        )


# ---------------------------------------------------------------------------
# HPC materialization
# ---------------------------------------------------------------------------


@pytest.fixture
def _require_hpc():
    if not _ysimulator_is_installed():
        pytest.skip("external/YSimulator not checked out in this environment")


def test_hpc_publish_materializes_news_link_and_reuses_sentinel_across_posts(
    sd_app, sd_client, _require_hpc
):
    from modules.scenario_editor.backend.hpc_session import hpc_session
    from YSimulator.YServer.classes.models import Article as HpcArticle
    from YSimulator.YServer.classes.models import Post as HpcPost

    from y_web.src.models import Exps

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase9-link-hpc-news")
    author_user_id = _seed_hpc_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="p1",
        parent_tmp_id=None,
        author_user_id=author_user_id,
        content="p1",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="p2",
        parent_tmp_id="p1",
        author_user_id=author_user_id,
        content="p2",
    )
    for tmp_id, url in (
        ("p1", "http://example.com/one"),
        ("p2", "http://example.com/two"),
    ):
        _put_post(
            client,
            exp_id,
            scenario_id,
            tmp_id,
            {
                "link_url": url,
                "link_kind": "news",
                "link_title": "Headline",
                "link_summary": "Summary",
            },
        )

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 201, resp.data
    id_mapping = resp.get_json()["id_mapping"]

    with sd_app.app_context():
        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            post1 = hsession.get(HpcPost, id_mapping["p1"])
            post2 = hsession.get(HpcPost, id_mapping["p2"])
            assert post1.news_id is not None
            assert post1.image_id is None
            article1 = hsession.get(HpcArticle, post1.news_id)
            article2 = hsession.get(HpcArticle, post2.news_id)
            assert article1.title == "Headline"
            assert article1.summary == "Summary"
            assert article1.link == "http://example.com/one"
            assert article1.website_id == article2.website_id  # same sentinel


def test_hpc_publish_materializes_image_link(sd_app, sd_client, _require_hpc):
    from modules.scenario_editor.backend.hpc_session import hpc_session
    from YSimulator.YServer.classes.models import Image as HpcImage
    from YSimulator.YServer.classes.models import Post as HpcPost

    from y_web.src.models import Exps

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase9-link-hpc-image")
    author_user_id = _seed_hpc_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_user_id,
        content="root",
    )
    _put_post(
        client,
        exp_id,
        scenario_id,
        "root",
        {
            "link_url": "http://example.com/pic.png",
            "link_kind": "image",
            "link_summary": "A picture.",
        },
    )

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 201, resp.data
    real_id = resp.get_json()["id_mapping"]["root"]

    with sd_app.app_context():
        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            post = hsession.get(HpcPost, real_id)
            assert post.image_id is not None
            assert post.news_id is None
            image = hsession.get(HpcImage, post.image_id)
            assert image.url == "http://example.com/pic.png"
            assert image.description == "A picture."
