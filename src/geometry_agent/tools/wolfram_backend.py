"""Wolfram Alpha fallback backend.

When SymPy-based structured tools return ``failed`` or time out, this module
calls the Wolfram Alpha Full Results API as a last-resort computation engine.

NOTE: An App ID is required. Set it via the ``WOLFRAM_APP_ID`` environment
variable or pass it to the constructor. Until a key is provided, all calls
return a "not configured" error without touching the network.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any


WOLFRAM_API_URL = "https://api.wolframalpha.com/v2/query"


class WolframBackend:
    """Thin wrapper around the Wolfram Alpha Full Results API.

    The backend is intentionally minimal: it sends a natural-language query
    and returns the plaintext result pods.  Callers should only use this as a
    fallback when local SymPy tools fail.
    """

    def __init__(self, app_id: str | None = None, timeout: int = 15):
        self.app_id = app_id or os.environ.get("WOLFRAM_APP_ID", "")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        """Whether the backend is configured (has an App ID)."""
        return bool(self.app_id)

    def query(self, query: str) -> dict[str, Any]:
        """Send a natural-language query to Wolfram Alpha.

        Args:
            query: e.g. "factor x^3 - 6x^2 + 11x - 6"

        Returns:
            {"success": True, "result": "...", "pods": [...]}
            or {"success": False, "error": "..."}
        """
        if not self.available:
            return {
                "success": False,
                "error": "Wolfram Alpha 未配置 App ID。请设置环境变量 WOLFRAM_APP_ID。",
            }
        params = {
            "input": query,
            "appid": self.app_id,
            "output": "json",
            "format": "plaintext",
        }
        url = f"{WOLFRAM_API_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GeometryAgent/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": f"Wolfram Alpha 请求失败: {e}"}

        pods = []
        result_text = ""
        try:
            query_result = data.get("queryresult", {})
            for pod in query_result.get("pods", []):
                title = pod.get("title", "")
                subpods = pod.get("subpods", [])
                texts = [sp.get("plaintext", "") for sp in subpods if sp.get("plaintext")]
                if texts:
                    pod_text = " | ".join(texts)
                    pods.append({"title": title, "text": pod_text})
                    if title in ("Result", "结果") and not result_text:
                        result_text = pod_text
            if not result_text and pods:
                result_text = pods[0]["text"]
            success = query_result.get("success", False)
        except Exception as e:
            return {"success": False, "error": f"解析 Wolfram 响应失败: {e}"}

        return {
            "success": success,
            "result": result_text,
            "pods": pods,
        }


# =====================================================================================
# Fallback dispatcher: try a local tool first, then Wolfram.
# =====================================================================================
def with_wolfram_fallback(
    local_fn,
    args: dict[str, Any],
    wolfram_query: str,
    backend: WolframBackend | None = None,
) -> dict[str, Any]:
    """Run a local tool; if it fails, fall back to Wolfram Alpha.

    Args:
        local_fn: a structured tool callable (returns dict with ``success``)
        args: keyword arguments for ``local_fn``
        wolfram_query: natural-language query for Wolfram if local fails
        backend: WolframBackend instance (created if None)
    """
    result = local_fn(**args)
    if result.get("success"):
        return result

    # Local failed → try Wolfram
    if backend is None:
        backend = WolframBackend()
    if not backend.available:
        return result  # Wolfram not configured, return local failure

    wa = backend.query(wolfram_query)
    if wa.get("success"):
        wa["fallback"] = "wolfram"
        wa["local_error"] = result.get("error", "")
        return wa
    return result


__all__ = ["WolframBackend", "with_wolfram_fallback"]
