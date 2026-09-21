"""OpenAI-compatible chat completion client — the Agent's "Think" layer.

Provider-agnostic over the OpenAI Chat Completions protocol, so it works with
DeepSeek, Qwen DashScope (compatible mode), Volcengine Ark (Doubao), OpenAI,
vLLM, one-api, etc. It is enabled ONLY when ``LLM_PROVIDER`` is not
``local`` and an API key is present; any failure is converted to ``LLMError``
so callers can transparently fall back to deterministic answers.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Sequence

from app.config.settings import get_settings


class LLMError(RuntimeError):
    pass


def is_llm_enabled() -> bool:
    settings = get_settings()
    return (settings.llm_provider or "local").lower() != "local" and bool(
        settings.llm_api_key
    )


def chat(
    messages: Sequence[Dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 900,
    timeout: float = 40.0,
) -> str:
    """Call ``{LLM_BASE_URL}/chat/completions`` and return the reply text."""
    settings = get_settings()
    base_url = (settings.llm_base_url or "").rstrip("/")
    if not base_url:
        raise LLMError("LLM_BASE_URL is not configured")
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")

    body = {
        "model": settings.llm_model,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"network error: {exc.reason}") from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected response shape: {str(data)[:200]}") from exc
    return (text or "").strip()
