"""Step-verification primitives, Pydantic models shared across verifier backends."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from geometry_agent.types import VerifyState


class Verdict(BaseModel):
    verified: VerifyState
    evidence: str = ""
    reason: str = ""
    lean_source: Optional[str] = None


class Step(BaseModel):
    id: str
    statement: str
    premise_ids: list[str] = Field(default_factory=list)
    justification: str = ""
