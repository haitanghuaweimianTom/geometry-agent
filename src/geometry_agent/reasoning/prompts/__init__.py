"""Prompt assets for the LLM Reasoning Agent (design/07 §2)."""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent


def _read(name: str) -> str:
    p = _PROMPT_DIR / name
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


SYSTEM_PROMPT: str = _read("system.txt")
ENHANCED_SYSTEM_PROMPT: str = _read("enhanced_system.txt")
FEWSHOT_TRIANGLE: str = _read("fewshot_triangle.txt")
FEWSHOT_PLANE: str = _read("fewshot_plane.txt")
FEWSHOT_ANALYTIC: str = _read("fewshot_analytic.txt")

_FEWSHOT_MAP = {
    "triangle": "fewshot_triangle.txt",
}

# Subject-based few-shot selection used by the enhanced reasoning agent.
_SUBJECT_FEWSHOT_MAP = {
    "plane_geometry": "fewshot_plane.txt",
    "triangle_solving": "fewshot_triangle.txt",
    "analytic_geometry": "fewshot_analytic.txt",
    "solid_geometry": "fewshot_plane.txt",  # fallback: no solid few-shot yet
}


def fewshot_for(topic: str = "triangle") -> str:
    """Return the few-shot prompt for a given topic (defaults to triangle)."""
    return _read(_FEWSHOT_MAP.get(topic, "fewshot_triangle.txt"))


def fewshot_for_subject(subject) -> str:
    """Return the few-shot prompt for a :class:`SubjectType` discipline.

    Falls back to the plane-geometry few-shot for unknown subjects.
    """
    key = subject.value if hasattr(subject, "value") else str(subject)
    return _read(_SUBJECT_FEWSHOT_MAP.get(key, "fewshot_plane.txt"))


__all__ = [
    "SYSTEM_PROMPT",
    "ENHANCED_SYSTEM_PROMPT",
    "FEWSHOT_TRIANGLE",
    "FEWSHOT_PLANE",
    "FEWSHOT_ANALYTIC",
    "fewshot_for",
    "fewshot_for_subject",
]
