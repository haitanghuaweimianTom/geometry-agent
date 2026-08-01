"""Adaptive tolerance model & three-state classification (design/05 §3)."""

from __future__ import annotations

from ..types import VerifyState


def tolerance(abs_tol: float, rel_tol: float, scale: float) -> float:
    """tol = max(abs_tol, rel_tol * scale)."""
    return max(float(abs_tol), float(rel_tol) * float(scale))


def classify(error: float, tol: float, mult: float = 3.0) -> VerifyState:
    """Three-state verdict.

    - error <= tol              -> TRUE
    - tol < error <= mult*tol   -> UNCERTAIN
    - error > mult*tol          -> FALSE
    """
    error = float(error)
    tol = float(tol)
    if error <= tol:
        return VerifyState.TRUE
    if error <= mult * tol:
        return VerifyState.UNCERTAIN
    return VerifyState.FALSE
