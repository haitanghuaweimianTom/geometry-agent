"""HTTP client for an OpenAI-compatible /chat/completions endpoint.

Falls back to an "offline" sentinel response when no api_key is configured or
the network call fails, so the rest of the pipeline never crashes
(design/07 §6 error recovery).
"""

from __future__ import annotations

from typing import Any

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

            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.config.temperature if temperature is None else temperature,
                "max_tokens": self.config.max_tokens,
            }
            if tools:
                payload["tools"] = tools
            url = self.base_url
            if not url.endswith("/chat/completions"):
                url = f"{url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            with httpx.Client(timeout=_TIMEOUT) as cx:
                r = cx.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            # Normalize reasoning-model responses: GLM-5.2 / deepseek-v4-pro put
            # chain-of-thought in `reasoning_content` and the final answer in
            # `content`. Keep both; if content is empty but reasoning exists,
            # surface reasoning so downstream parsers don't see an empty message.
            for ch in data.get("choices", []):
                msg = ch.get("message", {}) or {}
                if not msg.get("content") and msg.get("reasoning_content"):
                    msg["content"] = msg["reasoning_content"]
            return data
        except Exception as exc:
            return self._offline_response(messages, reason=f"request_failed: {exc!r}")

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
