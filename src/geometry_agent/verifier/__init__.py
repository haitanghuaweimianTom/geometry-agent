"""Constraint Verification Engine (design/05-Verifier.md)."""

from .engine import VerifierEngine
from .tolerance import classify, tolerance

__all__ = ["VerifierEngine", "classify", "tolerance"]
