from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Verdict(BaseModel):
    verified: Literal["true", "false", "uncertain"]
    evidence: str = ""
    reason: str = ""
    lean_source: str | None = None


class Step(BaseModel):
    id: str
    statement: str
    premise_ids: list[str] = Field(default_factory=list)
    justification: str = ""
