from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import requests


class UrlSummarizer:
    """Fetch a URL and summarize its textual content with an OpenAI-compatible LLM."""

    def __init__(self, config: dict[str, Any]):
        self._config = dict(config or {})
        self._model = str(self._config.get("model") or "").strip()
        self._base_url = str(self._config.get("base_url") or "").strip().rstrip("/")
        self._timeout = int(self._config.get("timeout") or 12)
        self._max_input_chars = int(self._config.get("max_input_chars") or 6000)
        self._max_summary_chars = int(self._config.get("max_summary_chars") or 500)
        self._headers = {"Content-Type": "application/json"}

    @staticmethod
    def build_config(
        *, model: str | None = None, base_url: str | None = None
    ) -> dict[str, Any] | None:
        model_name = str(model or "").strip()
        endpoint = str(base_url or "").strip()
        if not endpoint:
            endpoint = str(__import__("os").getenv("LLM_URL") or "").strip()
        if not endpoint:
            return None
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            endpoint = f"http://{endpoint}"
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/v1"):
            endpoint = endpoint[:-3].rstrip("/")
        if not model_name:
            model_name = "llama3.2:latest"
        return {
            "model": model_name,
            "base_url": endpoint,
            "timeout": 12,
            "max_input_chars": 6000,
            "max_summary_chars": 500,
        }

    def summarize_url(self, url: str) -> str:
        clean_url = str(url or "").strip()
        if not clean_url:
            return ""
        parsed = urlparse(clean_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        source_text = self._extract_text_from_url(clean_url)
        if not source_text:
            return ""

        return self._summarize_text(source_text)

    def _extract_text_from_url(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=self._timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        html = response.text or ""
        if not html:
            return ""

        # Strip scripts/styles and basic HTML tags to derive readable text.
        html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", " ", html)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        return text[: self._max_input_chars]

    def _summarize_text(self, text: str) -> str:
        chat_url = f"{self._base_url}/v1/chat/completions"
        prompt = (
            "Summarize the article content below in 2-4 concise sentences. "
            "Focus on key facts and avoid filler.\n\n"
            f"ARTICLE:\n{text}"
        )
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You summarize web articles accurately and concisely.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        response = requests.post(
            chat_url,
            json=payload,
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json() or {}
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            return ""
        return content[: self._max_summary_chars]
