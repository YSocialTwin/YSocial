"""Link cards (title, summary, image, short address) and clickable mentions in the IM chat pages."""

import json
import os
import sqlite3

import pytest

from y_web.src.im import link_preview as lp
from y_web.tests.test_im_admin_pages import im_app  # noqa: F401
from y_web.tests.test_im_observer_routes import observer  # noqa: F401

URL = "https://www.example.org/world/middle-east/2026/10/27/in-israel-turnout-hits-a-record-since-1973_abc123.html"


def test_short_url_keeps_the_host_and_the_end_of_the_address():
    short = lp.short_url(URL)
    assert short.startswith("example.org/…/") and len(short) <= 46
    assert lp.short_url("https://www.example.org/") == "example.org"
    assert lp.short_url("https://example.org/a") == "example.org/a"


def test_normalize_ignores_tracking_fragment_and_trailing_slash():
    assert lp.normalize("HTTPS://Example.org/a/?utm_source=x&id=2#top") == lp.normalize(
        "https://example.org/a?id=2"
    )


def test_strip_urls_removes_the_address_the_card_shows():
    text = f"Record turnout 🌍 {URL}\n{URL}"
    assert lp.strip_urls(text, [URL]) == "Record turnout 🌍"
    assert lp.strip_urls("no link here", [URL]) == "no link here"


def test_lookup_reads_the_snapshot_and_the_cache(tmp_path):
    folder = str(tmp_path)
    (tmp_path / lp.SNAPSHOT_FILE).write_text(
        json.dumps(
            {
                "feed_url": "f",
                "link": URL + "/",
                "title": "Turnout hits a record",
                "summary": "<p>The <b>highest</b> since 1973.</p>",
            }
        )
        + "\n"
    )
    info = lp.lookup(folder, URL)
    assert (
        info["title"] == "Turnout hits a record"
        and info["summary"] == "The highest since 1973."
    )
    assert info["image"] == "" and info["pending"] is True
    (tmp_path / lp.CACHE_FILE).write_text(
        json.dumps({lp.normalize(URL): {"image": "https://img.example.org/a.jpg"}})
    )
    info = lp.lookup(folder, URL)
    assert info["image"] == "https://img.example.org/a.jpg" and info["pending"] is False


def test_fetch_remote_refuses_private_addresses_and_remembers_the_failure(tmp_path):
    calls = []
    out = lp.fetch_remote(
        str(tmp_path), "http://127.0.0.1/secret", get=lambda *a, **k: calls.append(a)
    )
    assert calls == [] and out["image"] == "" and out["failed"]
    assert lp.lookup(str(tmp_path), "http://127.0.0.1/secret")["pending"] is False


def _seed(path):
    con = sqlite3.connect(path)
    mid, chat, sender = con.execute(
        "SELECT m.id, m.chat_id, m.sender_account_id FROM messages m JOIN chats c ON c.id = m.chat_id "
        "WHERE c.visibility = 'public' AND c.type != 'private' AND m.deleted_round IS NULL ORDER BY m.round_id DESC LIMIT 1"
    ).fetchone()
    target = con.execute(
        "SELECT id, username FROM accounts WHERE id != ? LIMIT 1", (sender,)
    ).fetchone()
    con.execute(
        "UPDATE messages SET text = ? WHERE id = ?", (f"Record turnout {URL}", mid)
    )
    con.execute(
        "INSERT INTO message_urls (message_id, url, normalized_url, domain) VALUES (?, ?, ?, ?)",
        (mid, URL, URL, "example.org"),
    )
    con.execute(
        "INSERT INTO mentions (message_id, mentioned_account_id, username) VALUES (?, ?, ?)",
        (mid, target[0], target[1]),
    )
    con.commit()
    con.close()
    return chat, target


def test_chat_page_shows_the_card_and_links_the_mention(observer):
    app, client, exp_id, info, path = observer
    chat, target = _seed(path)
    folder = os.path.dirname(path)
    with open(os.path.join(folder, lp.SNAPSHOT_FILE), "w") as handle:
        handle.write(
            json.dumps(
                {
                    "feed_url": "f",
                    "link": URL,
                    "title": "Turnout hits a record",
                    "summary": "The highest since 1973.",
                }
            )
            + "\n"
        )
    with open(os.path.join(folder, lp.CACHE_FILE), "w") as handle:
        json.dump(
            {lp.normalize(URL): {"image": "https://img.example.org/a.jpg"}}, handle
        )
    html = client.get(f"/{exp_id}/im/chat/{chat}").data.decode()
    assert f'href="{URL}"' in html and 'class="im-link-card has-image"' in html
    assert "Turnout hits a record" in html and "https://img.example.org/a.jpg" in html
    assert "example.org/…/" in html
    assert (
        '<p class="im-text">Record turnout</p>' in html
    )  # the address is in the card, not repeated in the text
    assert (
        f'href="/{exp_id}/im/profile/{target[0]}' in html
        and f">@{target[1]}</a>" in html
    )


def test_preview_endpoint_only_fetches_addresses_of_the_experiment(
    observer, monkeypatch
):
    app, client, exp_id, info, path = observer
    _seed(path)
    assert (
        client.get(f"/{exp_id}/im/api/link-preview?url=http://127.0.0.1/x").status_code
        == 404
    )
    monkeypatch.setattr(
        lp,
        "fetch_remote",
        lambda folder, url, **k: {
            "title": "T",
            "summary": "S",
            "image": "https://img.example.org/b.jpg",
        },
    )
    data = client.get(
        f"/{exp_id}/im/api/link-preview", query_string={"url": URL}
    ).get_json()
    assert data["image"] == "https://img.example.org/b.jpg"
