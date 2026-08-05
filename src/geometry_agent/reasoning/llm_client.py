"""HTTP client for an OpenAI-compatible /chat/completions endpoint.

Falls back to an "offline" sentinel response when no api_key is configured or
the network call fails, so the rest of the pipeline never crashes
(design/07 §6 error recovery).

Supports both synchronous (``chat``) and asynchronous (``achat``) calls,
plus streaming via ``achat_stream``.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from ..config import LLMConfig

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TIMEOUT = 60.0


class LLMClient:
    """Thin wrapper around an OpenAI-compatible chat-completions API."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        base = (self.config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.base_url = base
        self.api_key = self.config.api_key or ""
        self.model = self.config.model

    @property
    def is_offline(self) -> bool:
        return not self.api_key

    # ------------------------------------------------------------------ #
    # Synchronous API (backward-compatible)
    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call /chat/completions and return the parsed JSON response.

        Returns an offline-sentinel dict ({"offline": True, ...}) when no
        api_key is set or the request raises, so callers can degrade gracefully.
        """
        if self.is_offline:
            return self._offline_response(messages)
        try:
            import httpx

            payload = self._build_payload(messages, tools, temperature)
            url = self._chat_url()
            headers = self._headers()
            with httpx.Client(timeout=_TIMEOUT) as cx:
                r = cx.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            return self._normalize_response(data)
        except Exception as exc:
            return self._offline_response(messages, reason=f"request_failed: {exc!r}")

    # ------------------------------------------------------------------ #
    # Async API
    # ------------------------------------------------------------------ #
    async def achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Async version of :meth:`chat`."""
        if self.is_offline:
            return self._offline_response(messages)
        try:
            import httpx

            payload = self._build_payload(messages, tools, temperature)
            url = self._chat_url()
            headers = self._headers()
            async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
                r = await cx.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            return self._normalize_response(data)
        except Exception as exc:
            return self._offline_response(messages, reason=f"request_failed: {exc!r}")

    async def achat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream chat completions via SSE, yielding delta chunks.

        Each yielded dict has ``{"delta": {...}}`` for incremental content
        or ``{"tool_call": {...}}`` for tool call deltas.
        Yields a final ``{"done": True, "finish_reason": "..."}`` when complete.
        """
        if self.is_offline:
            yield {"delta": {"content": "[offline] LLM unavailable"}, "done": True, "finish_reason": "stop"}
            return
        try:
            import httpx

            payload = self._build_payload(messages, tools, temperature)
            payload["stream"] = True
            url = self._chat_url()
            headers = self._headers()

            async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
                async with cx.stream("POST", url, json=payload, headers=headers) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            yield {"done": True, "finish_reason": "stop"}
                            return
                        try:
                            import json as _json
                            chunk = _json.loads(data_str)
                            choice = (chunk.get("choices") or [{}])[0]
                            finish = choice.get("finish_reason")
                            delta = choice.get("delta") or {}
                            if finish:
                                yield {"done": True, "finish_reason": finish, "delta": delta}
                                return
                            yield {"delta": delta}
                        except Exception:
                            continue
        except Exception as exc:
            yield {"delta": {"content": f"[offline] LLM unavailable: {exc!r}"}, "done": True, "finish_reason": "error"}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _chat_url(self) -> str:
        url = self.base_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        return url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        for ch in data.get("choices", []):
            msg = ch.get("message", {}) or {}
            if not msg.get("content") and msg.get("reasoning_content"):
                msg["content"] = msg["reasoning_content"]
        return data

    def _offline_response(
        self,
        messages: list[dict[str, Any]] | None = None,
        reason: str = "no api_key configured",
    ) -> dict[str, Any]:
        return {
            "id": "offline",
            "object": "chat.completion",
            "offline": True,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[offline] LLM unavailable: {reason}.",
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }


__all__ = ["LLMClient"]