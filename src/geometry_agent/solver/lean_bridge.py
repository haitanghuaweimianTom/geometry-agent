"""Lean 4 formal verification bridge (design/08 §7, Phase 5 stub).

The real Lean integration translates a GeometryGraph + proof chain into Lean 4
propositions and invokes the Lean compiler. Until Lean is wired up this module
provides a stable interface that returns ``verified=False`` with an explicit
reason, so callers can feature-detect without crashing.
"""

from __future__ import annotations

from typing import Any

from ..config import SolverConfig
from ..types import GeometryGraph, ProofPlan


def verify_proof(
    graph: GeometryGraph,
    proof: ProofPlan | list[Any] | None = None,
    config: SolverConfig | None = None,
) -> dict:
    """Stub for Lean-based proof verification.

    Returns ``{"verified": False, "reason": "lean disabled"}`` when Lean is not
    enabled (default). When enabled but the Lean toolchain is unavailable the
    result carries ``reason="lean toolchain not found"``.
    """
    cfg = config or SolverConfig()
    if not cfg.lean_enabled:
        return {"verified": False, "reason": "lean disabled"}

    try:
        import shutil

        if shutil.which("lean") is None:
            return {"verified": False, "reason": "lean toolchain not found"}
    except Exception as exc:
        return {"verified": False, "reason": f"lean probe failed: {exc}"}

    return {"verified": False, "reason": "lean bridge not implemented"}
