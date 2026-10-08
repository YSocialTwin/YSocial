"""Fetch and parse a lightweight preview (title/summary) for a URL an
admin attaches to a draft post in Scenario Design's own thread/post
editor (piano di implementazione, Fase 9 follow-up: "link a una pagina
news/immagine nel composer", scoped to Scenario Design only, never the
live YWeb composer or runtime -- see docs/decisions.md for the explicit
scope confirmation).

Deliberately does **not** reuse YWeb core's
``y_web/src/llm/url_summarizer.py::UrlSummarizer``: that module lives in
``y_web`` (breaking this package's standalone testability, same reasoning
already documented in ``llm_client.py``'s module docstring), requires a
configured LLM backend to produce a summary, and has no SSRF guard and no
content-type branch for an image URL vs a news page -- three mismatches
with what this feature needs, not one. This module is a plain
``requests`` + stdlib ``html.parser`` extractor, no LLM call, same
dependency footprint as ``llm_client.py`` (``requests`` only).

Only this module knows about HTTP/``requests``/parsing -- the route
(``routes_threads.py``) and the materialization adapters
(``adapters/standard.py``/``adapters/hpc.py``) only ever see the plain
dict this module returns.
"""
from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 2_000_000  # 2 MB -- enough for any realistic HTML head/image probe
LINK_KIND_IMAGE = "image"
LINK_KIND_NEWS = "news"
VALID_LINK_KINDS = (LINK_KIND_IMAGE, LINK_KIND_NEWS)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ScenarioDesignLinkPreview"
)


class LinkPreviewError(Exception):
    """Raised with a machine-readable ``code`` (piano tecnico §15 uniform
    error envelope), same convention as ``MetadataMappingError``/
    ``LlmBackendError`` elsewhere in this package."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_unsafe_host(hostname: str) -> None:
    """SSRF guard: resolve *hostname* and refuse loopback/private/
    link-local/reserved addresses. This fetch is server-side, triggered
    by an admin pasting a URL into an authoring tool -- without this
    check, that admin tool becomes a way to probe the server's own
    internal network (piano tecnico §21, same "never trust a free-text
    URL" posture already applied to every other field in this package)."""
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise LinkPreviewError(
            "host_unresolvable", f"Could not resolve host '{hostname}'."
        ) from exc

    for family, _, _, _, sockaddr in addrinfo:
        ip_text = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise LinkPreviewError(
                "host_not_allowed",
                f"Host '{hostname}' resolves to a disallowed address ({ip_text}).",
            )


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise LinkPreviewError("missing_url", "link_url is required.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise LinkPreviewError(
            "unsupported_scheme", "Only http:// and https:// URLs are supported."
        )
    if not parsed.hostname:
        raise LinkPreviewError("invalid_url", "URL has no host.")
    _reject_unsafe_host(parsed.hostname)
    return url


class _TitleMetaParser(HTMLParser):
    """Minimal, dependency-free HTML head parser: ``<title>``,
    ``og:title``/``og:description`` (preferred, when present) falling
    back to the plain ``<title>`` tag and the ``name="description"``
    meta tag. No external HTML library (``lxml``/``beautifulsoup4``) --
    this package's standalone suite only depends on Flask + ``requests``
    (README.md "Requirements"), and stdlib's ``html.parser`` is
    sufficient for the handful of tags this needs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self.title = ""
        self.og_title = ""
        self.og_description = ""
        self.meta_description = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta":
            return
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        prop = attr_dict.get("property", "").lower()
        name = attr_dict.get("name", "").lower()
        content = attr_dict.get("content", "")
        if prop == "og:title" and content:
            self.og_title = content
        elif prop == "og:description" and content:
            self.og_description = content
        elif name == "description" and content:
            self.meta_description = content

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def fetch_link_preview(
    url: str,
    link_kind: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session=None,
) -> dict:
    """Fetch *url* and return ``{"title": str, "summary": str}``.

    ``link_kind`` must be ``"image"`` or ``"news"`` (``VALID_LINK_KINDS``):

    * ``"image"``: the response's ``Content-Type`` must be ``image/*`` --
      this function does not download or decode the image itself (no
      vision-model annotation here, unlike the live YWeb composer's
      ``minicpm-v`` path -- out of scope for this feature, see
      docs/decisions.md). ``title``/``summary`` come back empty; the
      admin can still fill ``link_summary`` by hand afterwards (used as
      the materialized ``Images.description``/``Image.description``).
    * ``"news"``: the response must be an HTML page; ``title`` prefers
      ``og:title`` over ``<title>``, ``summary`` prefers
      ``og:description`` over a plain ``<meta name="description">`` tag.
      Both default to ``""`` if absent -- never raised as an error, since
      a page with no discoverable title/summary is still a valid link to
      attach, just one the admin has to title by hand (same "never
      silently invent content" posture as everywhere else in this
      package).

    Never raises for a missing title/summary, only for a request that
    cannot be served at all (bad URL, disallowed host, network failure,
    wrong content-type for the declared kind).

    ``session`` defaults to the ``requests`` module itself (which exposes
    a module-level ``.get``) -- tests pass a fake object with a ``.get``
    method instead, same injectable-transport convention already used by
    ``llm_client.py::ScenarioLlmClient``, so this runs with no real
    network access in the standalone suite.
    """
    if link_kind not in VALID_LINK_KINDS:
        raise LinkPreviewError(
            "invalid_link_kind", f"link_kind must be one of {VALID_LINK_KINDS}."
        )
    clean_url = _validate_url(url)
    transport = session if session is not None else requests

    try:
        response = transport.get(
            clean_url,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
            stream=True,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout as exc:
        raise LinkPreviewError("fetch_timeout", "The link timed out.") from exc
    except requests.exceptions.RequestException as exc:
        raise LinkPreviewError("fetch_failed", f"Could not fetch URL: {exc}") from exc

    with response:
        if response.status_code >= 400:
            raise LinkPreviewError(
                "fetch_failed", f"URL returned HTTP {response.status_code}."
            )

        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()

        if link_kind == LINK_KIND_IMAGE:
            if not content_type.startswith("image/"):
                raise LinkPreviewError(
                    "not_an_image",
                    f"URL's Content-Type is '{content_type or 'unknown'}', not an image.",
                )
            return {"title": "", "summary": ""}

        # link_kind == "news"
        if content_type and "html" not in content_type and "text" not in content_type:
            raise LinkPreviewError(
                "not_a_page",
                f"URL's Content-Type is '{content_type}', not an HTML page.",
            )

        raw = b""
        for chunk in response.iter_content(chunk_size=65536):
            raw += chunk
            if len(raw) >= MAX_RESPONSE_BYTES:
                break
        try:
            html = raw.decode(response.encoding or "utf-8", errors="replace")
        except (LookupError, TypeError):
            html = raw.decode("utf-8", errors="replace")

        parser = _TitleMetaParser()
        try:
            parser.feed(html)
        except Exception:
            # Malformed markup is common on the open web -- a parse
            # failure degrades to "no title/summary found", never an
            # error surfaced to the admin (same posture as the
            # empty-title/summary case above).
            return {"title": "", "summary": ""}

        title = (parser.og_title or parser.title or "").strip()
        summary = (parser.og_description or parser.meta_description or "").strip()
        return {"title": title, "summary": summary}
