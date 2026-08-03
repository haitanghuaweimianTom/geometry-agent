"""Tool-calling schema (OpenAI function-calling format) and dispatcher.

Schemas cover verify / solve / search / graph_query / reflect (design/07 §4).
``dispatch`` executes a named tool against the live tools dict provided by the
pipeline (``GeometryPipeline._tools()``) and serialises Pydantic results to
plain JSON-able dicts.
"""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "verify",
            "description": (
                "Verify a geometric relation between two graph nodes. "
                "Returns {verified, evidence, measured}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rel": {
                        "type": "string",
                        "description": (
                            "Relation type, e.g. On, Parallel, Perpendicular, "
                            "Tangent, Equal, Collinear, Concentric, Intersect, "
                            "Inscribed, Similar, Congruent."
                        ),
                    },
                    "src": {"type": "string", "description": "Source node id."},
                    "dst": {"type": "string", "description": "Destination node id."},
                    "attrs": {
                        "type": "object",
                        "description": "Optional extra attributes for the verifier.",
                    },
                },
                "required": ["rel", "src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve",
            "description": (
                "Solve a system of equations (human-readable strings) and verify "
                "an optional goal. Returns {verified, solution, reason}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "equations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Equations like "AB/AC = AE/AD".',
                    },
                    "goal": {
                        "type": "string",
                        "description": "Optional proposition to verify, e.g. AB*AC = AD*AE.",
                    },
                },
                "required": ["equations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Retrieve relevant geometry theorems from the theorem database (RAG).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword query, e.g. 圆周角."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_query",
            "description": "Query the geometry graph for facts or a subgraph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Graph query string."}
                },
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reflect",
            "description": (
                "Trigger self-reflection after a verification failure and produce "
                "a revised proof plan. Called when verify returns false."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "failure": {"type": "string", "description": "Description of what failed."},
                    "plan": {"type": "object", "description": "Current (failing) plan."},
                    "history": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Prior reflection history.",
                    },
                },
                "required": ["failure"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_step",
            "description": (
                "Assert a proof-step conclusion that must be verified before proceeding. "
                "Junior/senior modes verify algebraically; competition mode verifies via Lean. "
                "Call this for every non-trivial conclusion, not for raw arithmetic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "step_id": {
                        "type": "string",
                        "description": "Unique id for this step, e.g. \"s1\", \"s2\".",
                    },
                    "statement": {
                        "type": "string",
                        "description": "The conclusion being asserted (e.g. \"AB/AC = AE/AD\").",
                    },
                    "premise_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ids of previously verified steps this depends on.",
                    },
                    "justification": {
                        "type": "string",
                        "description": "Which lemma/method/axiom justifies the step (e.g. \"相似三角形AA\").",
                    },
                },
                "required": ["step_id", "statement", "justification"],
            },
        },
    },
]

_TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}

# Extended tools (code execution + advanced geometry methods) declared in
# ``geometry_agent.tools.registry``. We register their names here so
# :func:`dispatch` transparently passes them through to the tools dict,
# without importing the registry (which would create a circular import).
_EXTENDED_TOOL_NAMES: set[str] = {
    "execute_code",
    "complex_method",
    "coordinate_method",
    "projective_method",
}
_TOOL_NAMES |= _EXTENDED_TOOL_NAMES


def claim_step(**kwargs: Any) -> dict[str, Any]:
    return {"status": "pending_verification", "step": kwargs}


def _serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, tuple):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def dispatch(tool_name: str, args: Any, tools_dict: dict[str, Any]) -> Any:
    """Execute ``tool_name`` with ``args`` against ``tools_dict``.

    Returns a JSON-able dict. Unknown tools and exceptions are returned as
    ``{"error": ...}`` rather than raised, so the LLM loop can continue.
    """
    if tool_name not in _TOOL_NAMES:
        return {"error": f"unknown tool: {tool_name}"}

    fn = tools_dict.get(tool_name) if tools_dict else None
    if fn is None:
        if tool_name == "reflect":
            return {"status": "noop", "note": "reflection handled by the agent loop"}
        return {"error": f"tool not provided: {tool_name}"}

    call_args = args or {}
    try:
        if isinstance(call_args, dict):
            result = fn(**call_args)
        elif isinstance(call_args, (list, tuple)):
            result = fn(*call_args)
        else:
            result = fn(call_args)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

    return _serialize(result)


__all__ = ["TOOL_SCHEMAS", "claim_step", "dispatch"]
