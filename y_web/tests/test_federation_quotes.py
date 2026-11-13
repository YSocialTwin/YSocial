"""P4 / E3: attribution of shared content in the views (read-only helper over federation_quoted, macro, templates)."""

import os
import sqlite3

import pytest

from y_web.src.federation import quotes, service
from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)

TEMPLATES = os.path.join(os.path.dirname(__file__), "..", "templates")


def _db(path, column, rows, table=True):
    conn = sqlite3.connect(path)
    if table:
        conn.execute(
            f"CREATE TABLE federation_quoted ({column} TEXT PRIMARY KEY, author_name TEXT, global_agent_id TEXT, "
            "member TEXT, source_ref TEXT, text_excerpt TEXT)"
        )
        conn.executemany(f"INSERT INTO federation_quoted VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


ROW = (
    "7",
    "ann",
    "g2",
    "microblogging",
    "ysocial://1/microblogging/post/3",
    "original words",
)


@pytest.mark.parametrize("column", ["post_id", "photo_id", "message_id", "local_id"])
def test_every_runtime_key_column_is_read(tmp_path, column):
    path = str(tmp_path / "db.sqlite")
    _db(path, column, [ROW])
    got = quotes.read_quotes(path)
    assert got == {
        "7": {
            "author_name": "ann",
            "member": "microblogging",
            "platform": "Microblogging",
            "excerpt": "original words",
            "source_ref": "ysocial://1/microblogging/post/3",
        }
    }


def test_a_missing_file_table_or_column_gives_nothing(tmp_path):
    assert quotes.read_quotes(str(tmp_path / "nope.sqlite")) == {}
    path = str(tmp_path / "empty.sqlite")
    _db(path, "post_id", [], table=False)
    assert quotes.read_quotes(path) == {}
    other = str(tmp_path / "other.sqlite")
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE federation_quoted (x TEXT)")
    conn.commit()
    conn.close()
    assert quotes.read_quotes(other) == {}


def test_the_database_is_never_written(tmp_path):
    path = str(tmp_path / "db.sqlite")
    _db(path, "post_id", [ROW])
    before = os.stat(path).st_mtime_ns
    quotes.read_quotes(path)
    assert os.stat(path).st_mtime_ns == before
    assert not os.path.exists(path + "-wal") and not os.path.exists(path + "-journal")


def test_an_unknown_platform_keeps_the_member_name():
    assert (
        quotes.platform_label("forum") == "Forum"
        and quotes.platform_label("my-member") == "my-member"
    )


def test_outside_a_world_simulation_nothing_is_read(world, monkeypatch):  # noqa: F811
    app, exps, tmp = world

    def boom(path):
        raise AssertionError("the database must not be opened")

    monkeypatch.setattr(quotes, "read_quotes", boom)
    with app.test_request_context():
        assert quotes.quotes_for(exps["microblogging"]) == {}
        assert quotes.federation_quote(exps["microblogging"], 7) is None


def test_inside_a_world_simulation_the_rows_are_filtered_and_cached_per_request(
    world, monkeypatch
):  # noqa: F811
    app, exps, tmp = world
    calls = []
    monkeypatch.setattr(
        service,
        "world_simulation_of",
        lambda exp_id: {"id": 1, "name": "w", "status": "stopped"},
    )
    monkeypatch.setattr(quotes, "_database_path", lambda exp_id: "fake")
    monkeypatch.setattr(
        quotes,
        "read_quotes",
        lambda path, names=None: calls.append(path)
        or {"7": {"author_name": "ann"}, "8": {"author_name": "bob"}},
    )
    with app.test_request_context():
        assert quotes.quotes_for(1, [7]) == {"7": {"author_name": "ann"}}
        calls.clear()
        assert quotes.federation_quote(1, 7) == {"author_name": "ann"}
        assert quotes.federation_quote(1, 8) == {"author_name": "bob"}
        assert quotes.federation_quote(1, 9) is None
        assert len(calls) == 1  # one read of the table for the whole request


def test_an_error_never_reaches_the_page(world, monkeypatch):  # noqa: F811
    app, exps, tmp = world

    def boom(exp_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(service, "world_simulation_of", boom)
    with app.test_request_context():
        assert quotes.quotes_for(1) == {} and quotes.federation_quote(1, 7) is None


def test_the_block_is_escaped_and_empty_without_a_quote():
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATES), autoescape=True)
    env.globals["_"] = lambda text, **kw: text % kw
    tpl = env.from_string(
        '{% from "shared/federation_quote.html" import federation_quote_block %}{{ federation_quote_block(q) }}'
    )
    assert tpl.render(q=None).strip() == ""
    html = tpl.render(
        q={
            "author_name": "<script>x</script>",
            "platform": "Forum",
            "excerpt": "a <b>b</b>",
        }
    )
    assert (
        "Shared from" in html
        and "Forum" in html
        and "<script>" not in html
        and "&lt;script&gt;" in html
        and "<b>" not in html
    )


@pytest.mark.parametrize(
    "path",
    [
        "microblogging/components/posts.html",
        "microblogging/components/thread-post.html",
        "forum/components/posts.html",
        "forum/components/thread-post.html",
        "photo/components/posts.html",
        "@instant_messaging/im/_message.html",
    ],
)
def test_the_views_call_the_helper(path):
    if path.startswith("@instant_messaging/"):
        from y_web.tests._platform_repos import platform_template

        text = platform_template("YInstantMessaging", path.split("/", 1)[1])
    else:
        with open(os.path.join(TEMPLATES, path)) as fh:
            text = fh.read()
    assert "federation_quote_block(federation_quote(exp_id" in text


def test_dating_pages_show_no_attribution():
    for root, _dirs, files in os.walk(os.path.join(TEMPLATES, "dating")):
        for f in files:
            with open(os.path.join(root, f)) as fh:
                assert "federation_quote" not in fh.read()
