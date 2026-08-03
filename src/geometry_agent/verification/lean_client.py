"""HTTP client for the Lean 4 verification service on rdzs02."""
from __future__ import annotations

import requests

from geometry_agent.types import VerifyState
from geometry_agent.verification._models import Step, Verdict


_LEAN_HEADER = (
    "import Lean\nopen Lean\n\n"
)


def _to_lean_expr(stmt: str) -> str:
    """Map a claim string to a Lean expression stub."""
    s = stmt.replace("^", "**").replace("sqrt", "Real.sqrt").replace("π", "Real.pi")
    s = s.replace("·", "*").replace("×", "*").replace("÷", "/")
    return s


class LeanStepVerifier:
    def __init__(self, endpoint: str, timeout_s: int = 10):
        self.endpoint = endpoint.rstrip("/") + "/verify"
        self.timeout_s = timeout_s

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        premises_lines = "\n".join(f"-- premise {p.id}: {p.statement}" for p in premises)
        concl = _to_lean_expr(step.statement)
        lean_src = (
            _LEAN_HEADER
            + premises_lines + ("\n" if premises else "")
            + f"theorem step_{step.id} : {concl} := by\n"
            + "  simp <;> decide <;> ring_nf <;> norm_num\n"
        )
        try:
            resp = requests.post(
                self.endpoint,
                json={"premises": [p.statement for p in premises],
                      "conclusion": step.statement,
                      "lean_source": lean_src},
                timeout=self.timeout_s,
            )
            data = resp.json()
            if data.get("verified"):
                return Verdict(verified=VerifyState.TRUE, evidence=data.get("output", ""),
                               lean_source=lean_src)
            return Verdict(verified=VerifyState.FALSE, evidence=data.get("output", ""),
                           reason=data.get("error", "lean rejected"),
                           lean_source=lean_src)
        except requests.RequestException as e:
            return Verdict(verified=VerifyState.UNCERTAIN,
                           reason=f"lean service unreachable: {e}",
                           lean_source=lean_src)
        except Exception as e:
            return Verdict(verified=VerifyState.UNCERTAIN,
                           reason=f"lean client error: {e}",
                           lean_source=lean_src)
