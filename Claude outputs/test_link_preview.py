"""Standalone tests for link_preview.py -- Fase 9 follow-up ("link a una
pagina news/immagine nel composer", scoped to Scenario Design only, see
docs/decisions.md). A fake ``session``-like object (same injectable-
transport convention as test_llm_client.py::_ScriptedSession) stands in
for ``requests``, so these run with no real network access. URLs use
literal IP addresses (``93.184.216.34`` is a real, routable, non-private
public address -- example.com's; never actually dialed here since the
session is fake) specifically so the SSRF host-resolution step itself
runs for real (``socket.getaddrinfo`` on a literal IP needs no DNS/
network) without this suite depending on DNS or network reachability.
"""
import pytest

from modules.scenario_editor.backend.link_preview import (
    LINK_KIND_IMAGE,
    LINK_KIND_NEWS,
    LinkPreviewError,
    fetch_link_preview,
)

PUBLIC_IP = "93.184.216.34"


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, body=b""):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.encoding = "utf-8"

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response


# ---------------------------------------------------------------------
# URL validation / SSRF guard -- exercised with no fake session at all,
# since these all fail before any HTTP call would be made.
# ---------------------------------------------------------------------

def test_rejects_missing_url():
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview("", LINK_KIND_NEWS)
    assert exc_info.value.code == "missing_url"


def test_rejects_non_http_scheme():
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview("ftp://example.com/file", LINK_KIND_NEWS)
    assert exc_info.value.code == "unsupported_scheme"


def test_rejects_invalid_link_kind():
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{PUBLIC_IP}/", "video")
    assert exc_info.value.code == "invalid_link_kind"


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "169.254.0.1", "10.0.0.5", "0.0.0.0"],
)
def test_rejects_loopback_private_and_link_local_hosts(host):
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{host}/", LINK_KIND_NEWS)
    assert exc_info.value.code == "host_not_allowed"


def test_rejects_unresolvable_host(monkeypatch):
    # Patched rather than relying on a real DNS failure for an
    # ".invalid" host: this suite must stay network-independent, and a
    # live resolver's behavior for an unresolvable name varies by
    # environment (immediate NXDOMAIN vs. a slow/absent-network hang).
    import socket

    import modules.scenario_editor.backend.link_preview as link_preview_module

    def _raise_gaierror(hostname, port):
        raise socket.gaierror("mocked: name or service not known")

    monkeypatch.setattr(link_preview_module.socket, "getaddrinfo", _raise_gaierror)

    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(
            "http://this-host-does-not-exist.invalid/", LINK_KIND_NEWS
        )
    assert exc_info.value.code == "host_unresolvable"


# ---------------------------------------------------------------------
# image kind
# ---------------------------------------------------------------------

def test_image_kind_accepts_image_content_type():
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "image/jpeg"}))
    result = fetch_link_preview(
        f"http://{PUBLIC_IP}/photo.jpg", LINK_KIND_IMAGE, session=session
    )
    assert result == {"title": "", "summary": ""}
    assert session.calls[0][0] == f"http://{PUBLIC_IP}/photo.jpg"


def test_image_kind_rejects_non_image_content_type():
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "text/html"}))
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{PUBLIC_IP}/page", LINK_KIND_IMAGE, session=session)
    assert exc_info.value.code == "not_an_image"


# ---------------------------------------------------------------------
# news kind -- title/summary extraction
# ---------------------------------------------------------------------

def test_news_kind_prefers_og_tags_over_plain_title():
    html = b"""<html><head>
        <title>Plain title</title>
        <meta property="og:title" content="OG Title Wins">
        <meta name="description" content="Plain description">
        <meta property="og:description" content="OG description wins">
        </head><body>ignored</body></html>"""
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "text/html; charset=utf-8"}, html))
    result = fetch_link_preview(f"http://{PUBLIC_IP}/article", LINK_KIND_NEWS, session=session)
    assert result == {"title": "OG Title Wins", "summary": "OG description wins"}


def test_news_kind_falls_back_to_plain_title_and_meta_description():
    html = b"""<html><head>
        <title>Plain title only</title>
        <meta name="description" content="Plain description only">
        </head><body></body></html>"""
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "text/html"}, html))
    result = fetch_link_preview(f"http://{PUBLIC_IP}/article", LINK_KIND_NEWS, session=session)
    assert result == {"title": "Plain title only", "summary": "Plain description only"}


def test_news_kind_degrades_to_empty_strings_when_nothing_found():
    html = b"<html><head></head><body>no title or meta here</body></html>"
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "text/html"}, html))
    result = fetch_link_preview(f"http://{PUBLIC_IP}/article", LINK_KIND_NEWS, session=session)
    assert result == {"title": "", "summary": ""}


def test_news_kind_rejects_non_html_content_type():
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "application/pdf"}))
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{PUBLIC_IP}/doc.pdf", LINK_KIND_NEWS, session=session)
    assert exc_info.value.code == "not_a_page"


def test_news_kind_malformed_markup_degrades_instead_of_raising():
    html = b"<html><head><title>Unterminated"
    session = _FakeSession(_FakeResponse(200, {"Content-Type": "text/html"}, html))
    result = fetch_link_preview(f"http://{PUBLIC_IP}/broken", LINK_KIND_NEWS, session=session)
    assert result["title"] in ("Unterminated", "")  # html.parser tolerates this; never raises


# ---------------------------------------------------------------------
# transport-level failures
# ---------------------------------------------------------------------

def test_http_error_status_raises_fetch_failed():
    session = _FakeSession(_FakeResponse(404, {"Content-Type": "text/html"}))
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{PUBLIC_IP}/missing", LINK_KIND_NEWS, session=session)
    assert exc_info.value.code == "fetch_failed"


def test_timeout_raises_fetch_timeout():
    import requests

    session = _FakeSession(exc=requests.exceptions.Timeout("timed out"))
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{PUBLIC_IP}/slow", LINK_KIND_NEWS, session=session)
    assert exc_info.value.code == "fetch_timeout"


def test_connection_error_raises_fetch_failed():
    import requests

    session = _FakeSession(exc=requests.exceptions.ConnectionError("refused"))
    with pytest.raises(LinkPreviewError) as exc_info:
        fetch_link_preview(f"http://{PUBLIC_IP}/down", LINK_KIND_NEWS, session=session)
    assert exc_info.value.code == "fetch_failed"
