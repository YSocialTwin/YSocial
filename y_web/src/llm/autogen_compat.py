from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import mimetypes
import os
import re
from typing import Any
from urllib.parse import urlparse

import requests


_IMAGE_TAG_RE = re.compile(r"<img\s+([^>\s]+)\s*>", re.IGNORECASE)


@dataclass
class _NormalizedLLMConfig:
    model: str | None
    base_url: str | None
    api_key: str | None
    timeout: float | None
    temperature: float | None
    max_tokens: int | None
    backend_hint: str | None


def _coerce_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
            elif isinstance(item, str) and item.strip():
                chunks.append(item.strip())
        return "\n".join(chunks).strip()
    if content is None:
        return ""
    return str(content)


def _normalize_llm_config(llm_config: dict | None) -> _NormalizedLLMConfig:
    llm_config = llm_config or {}
    config_list = llm_config.get("config_list") or [{}]
    if not isinstance(config_list, list) or not config_list:
        config_list = [{}]
    primary = config_list[0] or {}
    api_key = primary.get("api_key")
    if not api_key or api_key == "NULL":
        api_key = "EMPTY"
    return _NormalizedLLMConfig(
        model=primary.get("model"),
        base_url=primary.get("base_url"),
        api_key=api_key,
        timeout=primary.get("timeout"),
        temperature=llm_config.get("temperature"),
        max_tokens=llm_config.get("max_tokens"),
        backend_hint=(
            primary.get("backend")
            or primary.get("provider")
            or primary.get("api_format")
        ),
    )


def _looks_like_ollama(cfg: _NormalizedLLMConfig) -> bool:
    backend_hint = str(cfg.backend_hint or "").strip().lower()
    if backend_hint == "ollama":
        return True
    if backend_hint in {"openai", "open_ai", "vllm"}:
        return False

    base_url = str(cfg.base_url or "").strip().lower()
    if not base_url:
        return False
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    netloc = (parsed.netloc or "").lower()
    env_backend = str(os.getenv("LLM_BACKEND") or "").strip().lower()
    env_url = str(os.getenv("LLM_URL") or "").strip().rstrip("/")
    cfg_url = str(cfg.base_url or "").strip().rstrip("/")
    if env_backend == "ollama" and env_url and cfg_url and env_url == cfg_url:
        return True
    return (
        "ollama" in base_url
        or "ollama" in hostname
        or "ollama" in netloc
        or parsed.port == 11434
        or ":11434" in base_url
        or (
            (cfg.api_key or "").upper() in {"", "NULL", "EMPTY"}
            and bool(cfg.model)
            and ":" in str(cfg.model)
        )
    )


def _build_chat_model(llm_config: dict | None):
    cfg = _normalize_llm_config(llm_config)
    if _looks_like_ollama(cfg):
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError(
                "LangChain Ollama support is required for Ollama endpoints. Install `langchain-ollama`."
            ) from exc

        kwargs = {}
        if cfg.model:
            kwargs["model"] = cfg.model
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url.rsplit("/v1", 1)[0]
        if cfg.temperature is not None:
            kwargs["temperature"] = cfg.temperature
        if cfg.max_tokens is not None:
            kwargs["num_predict"] = cfg.max_tokens
        return ChatOllama(**kwargs)

    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    kwargs = {}
    if cfg.model:
        kwargs["model"] = cfg.model
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    if cfg.timeout is not None:
        kwargs["timeout"] = cfg.timeout
    if cfg.temperature is not None:
        kwargs["temperature"] = cfg.temperature
    if cfg.max_tokens is not None:
        kwargs["max_tokens"] = cfg.max_tokens
    return ChatOpenAI(**kwargs)


def _chat_completions_url(base_url: str | None) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("LLM base_url is required")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _image_url_to_data_url(image_url: str) -> str:
    source = str(image_url or "").strip()
    if not source or source.startswith("data:"):
        return source
    response = requests.get(
        source,
        timeout=120,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
    if not content_type:
        guessed, _ = mimetypes.guess_type(source)
        content_type = guessed or "image/jpeg"
    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _invoke_chat_completions(*, llm_config: dict | None, messages: list[dict[str, Any]]) -> str:
    cfg = _normalize_llm_config(llm_config)
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
    }
    if cfg.temperature is not None:
        payload["temperature"] = cfg.temperature
    if cfg.max_tokens is not None and int(cfg.max_tokens) > 0:
        payload["max_tokens"] = int(cfg.max_tokens)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key or 'EMPTY'}",
    }
    response = requests.post(
        _chat_completions_url(cfg.base_url),
        headers=headers,
        data=json.dumps(payload),
        timeout=cfg.timeout or 120,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return _coerce_content_to_text(data["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        raise RuntimeError(f"Unexpected LLM response schema: {data!r}") from exc


def _invoke_text_model(*, llm_config: dict | None, system_prompt: str, user_prompt: str) -> str:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception:
        HumanMessage = None
        SystemMessage = None

    if HumanMessage is not None and SystemMessage is not None:
        try:
            model = _build_chat_model(llm_config)
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=user_prompt))
            response = model.invoke(messages)
            return _coerce_content_to_text(getattr(response, "content", response))
        except Exception:
            pass

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return _invoke_chat_completions(llm_config=llm_config, messages=messages)


def _invoke_vision_model(
    *,
    llm_config: dict | None,
    system_prompt: str,
    user_prompt: str,
) -> str:
    match = _IMAGE_TAG_RE.search(user_prompt or "")
    image_url = match.group(1).strip() if match else ""
    cleaned_prompt = _IMAGE_TAG_RE.sub("", user_prompt or "").strip()
    data_url = ""
    if image_url:
        try:
            data_url = _image_url_to_data_url(image_url)
        except Exception:
            data_url = ""
            cleaned_prompt = f"{cleaned_prompt}\nImage URL: {image_url}".strip()
    content = []
    if cleaned_prompt:
        content.append({"type": "text", "text": cleaned_prompt})
    if data_url:
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = _build_chat_model(llm_config)
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=content or cleaned_prompt))
        response = model.invoke(messages)
        return _coerce_content_to_text(getattr(response, "content", response))
    except Exception:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content or cleaned_prompt})
        return _invoke_chat_completions(llm_config=llm_config, messages=messages)


class AssistantAgent:
    def __init__(
        self,
        name: str,
        llm_config: dict | None = None,
        system_message: str = "",
        max_consecutive_auto_reply: int = 0,
        human_input_mode: str | None = None,
        **_: Any,
    ) -> None:
        self.name = name
        self.llm_config = llm_config or {}
        self.system_message = system_message or ""
        self.max_consecutive_auto_reply = max_consecutive_auto_reply or 0
        self.human_input_mode = human_input_mode
        self.chat_messages: dict[AssistantAgent, list[dict[str, Any]]] = {}

    def _generate_reply(self, message: str) -> str:
        return _invoke_text_model(
            llm_config=self.llm_config,
            system_prompt=self.system_message,
            user_prompt=message,
        )

    def _store_transcript(self, peer_agent: "AssistantAgent", transcript: list[dict[str, Any]]) -> None:
        copied = [dict(entry) for entry in transcript]
        self.chat_messages[peer_agent] = copied
        peer_agent.chat_messages[self] = [dict(entry) for entry in transcript]

    def initiate_chat(
        self,
        peer_agent: "AssistantAgent",
        message: str,
        silent: bool = True,
        max_round: int | None = None,
        max_turns: int | None = None,
    ) -> None:
        del silent, max_round, max_turns
        transcript: list[dict[str, Any]] = []

        peer_reply = peer_agent._generate_reply(message)
        transcript.append({"content": peer_reply})

        if self.max_consecutive_auto_reply > 0:
            own_reply = self._generate_reply(peer_reply)
            transcript.append({"content": own_reply})

        self._store_transcript(peer_agent, transcript)

    def last_message(self, peer_agent: "AssistantAgent") -> dict[str, Any] | None:
        messages = self.chat_messages.get(peer_agent) or []
        return messages[-1] if messages else None

    def reset(self) -> None:
        self.chat_messages = {}


class MultimodalConversableAgent(AssistantAgent):
    def _generate_reply(self, message: str) -> list[dict[str, str]]:
        text = _invoke_vision_model(
            llm_config=self.llm_config,
            system_prompt=self.system_message,
            user_prompt=message,
        )
        return [{"text": text}]
