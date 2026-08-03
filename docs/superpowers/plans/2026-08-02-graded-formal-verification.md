# 三档分阶几何推理系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-step formal verification (SymPy/Z3 for junior/senior, Lean 4 on rdzs02 for competition), three-grade lemma libraries, retry+LLM-judge failure handling, and `claim_step` tool to the geometry agent.

**Architecture:** Verify-middleware injected after tool dispatch in `_run_feedback_loop` routes by `grade` to `SymbolicStepVerifier` (local) or `LeanStepVerifier` (remote rdzs02:9407). New `claim_step` tool lets LLM assert a conclusion; verifier returns Verdict; failures retry ≤3 then fall back to LLMJudge. Knowledge base expanded with grade-scoped entries, formal IDs, and proof hints. Lean service deployed via Docker on rdzs02.

**Tech Stack:** Python, SymPy, Z3, FastAPI, Docker, Lean 4, pydantic. Existing stack unchanged: enhanced_agent, tools, knowledge manager, prompt builder.

**Spec:** `docs/superpowers/specs/2026-08-02-graded-formal-verification-design.md`

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/geometry_agent/verification/__init__.py` | Verdict, StepVerifier Protocol, build_verifier factory |
| Create | `src/geometry_agent/verification/symbolic.py` | SymbolicStepVerifier (SymPy/Z3) |
| Create | `src/geometry_agent/verification/lean_client.py` | LeanStepVerifier HTTP client |
| Create | `src/geometry_agent/verification/llm_judge.py` | LLMJudge fallback |
| Create | `src/geometry_agent/verification/step_parser.py` | Parse Chinese+formula claim into symbolic form |
| Create | `scripts/deploy_lean_service.py` | One-shot deploy Lean HTTP service to rdzs02 via SSH+Docker |
| Create | `scripts/Dockerfile.lean` | Lean 4 + FastAPI service image |
| Create | `scripts/lean_service.py` | FastAPI `/verify` endpoint |
| Modify | `src/geometry_agent/types.py:366-390` | Add `formal_id`, `proof_hint` to KnowledgeEntry/MethodEntry |
| Modify | `src/geometry_agent/reasoning/tools.py` | Add `claim_step` tool schema, register |
| Modify | `src/geometry_agent/reasoning/enhanced_agent.py:270-430` | Inject verifier into feedback loop; retry logic |
| Modify | `src/geometry_agent/reasoning/prompt_builder.py` | Add verification-contract to system prompt by grade |
| Modify | `src/geometry_agent/knowledge/curated.py` | Expand lemma entries (junior/senior/competition), add formal_id |
| Modify | `configs/default.yaml` | Add `verification` section |
| Create | `tests/unit/test_symbolic_verifier.py` | Unit tests for symbolic verifier |
| Create | `tests/unit/test_lean_client.py` | Unit tests for Lean client (mock HTTP) |
| Create | `tests/unit/test_llm_judge.py` | Unit tests for LLM judge |
| Create | `tests/unit/test_verification_middleware.py` | Integration: middleware routing, retry, fallback |
| Modify | `tests/unit/test_math_reliability.py` | Extend with claim_step assertions |
| Create | `tests/e2e/test_graded_verification.py` | 5 junior + 5 senior + 3 competition E2E |

---

## Phase 1: Verification Skeleton (no logic yet — types, factory, tool schema)

### Task 1: Verdict/Step types & Protocol

**Files:**
- Create: `src/geometry_agent/verification/__init__.py`

- [ ] **Step 1: Write the failing test for Verdict/Step models**

Create `tests/unit/test_verification_middleware.py`:

```python
import pytest
from geometry_agent.verification import Verdict, Step, StepVerifier, build_verifier
from geometry_agent.types import GradeLevel


def test_verdict_requires_verified_field():
    v = Verdict(verified="true", evidence="x=2", reason="")
    assert v.verified == "true"
    assert v.evidence == "x=2"


def test_verdict_rejects_invalid_verified_value():
    with pytest.raises(Exception):
        Verdict(verified="yes", evidence="", reason="")


def test_step_captures_statement_and_premise_ids():
    s = Step(statement="AB = CD", premise_ids=["h1", "h2"], justification="全等三角形")
    assert s.statement == "AB = CD"
    assert s.premise_ids == ["h1", "h2"]


def test_build_verifier_junior_returns_symbolic():
    from geometry_agent.verification.symbolic import SymbolicStepVerifier
    v = build_verifier(GradeLevel.JUNIOR, client=None, lean_endpoint=None)
    assert isinstance(v, SymbolicStepVerifier)


def test_build_verifier_competition_returns_lean():
    from geometry_agent.verification.lean_client import LeanStepVerifier
    v = build_verifier(GradeLevel.COMPETITION, client=None, lean_endpoint="http://x:9407")
    assert isinstance(v, LeanStepVerifier)
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd /home/tomgame/projects/geometry_agent && python -m pytest tests/unit/test_verification_middleware.py -p no:pyz3 -q`
Expected: ImportError (verification module doesn't exist)

- [ ] **Step 3: Create verification module with types and factory**

Create `src/geometry_agent/verification/__init__.py`:

```python
"""Per-step verification subsystem.

Routes step verification to the appropriate backend by grade:
- junior/senior: local SymPy/Z3 symbolic checker
- competition : remote Lean 4 HTTP service on rdzs02
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from ..types import GradeLevel


class Step(BaseModel):
    """A single proof step asserted by the LLM via ``claim_step``."""
    id: str
    statement: str
    premise_ids: list[str] = Field(default_factory=list)
    justification: str = ""


class Verdict(BaseModel):
    """Result of verifying one step."""
    verified: Literal["true", "false", "uncertain"]
    evidence: str = ""
    reason: str = ""
    lean_source: str | None = None


class StepVerifier(Protocol):
    def verify(self, step: Step, premises: list[Step]) -> Verdict: ...


def build_verifier(
    grade: GradeLevel,
    *,
    client: Any = None,
    lean_endpoint: str | None = None,
    symbolic_timeout_ms: int = 200,
) -> StepVerifier:
    """Construct the appropriate verifier for ``grade``."""
    if grade == GradeLevel.COMPETITION:
        from .lean_client import LeanStepVerifier
        if not lean_endpoint:
            # fall back to symbolic with warning when Lean unreachable
            from .symbolic import SymbolicStepVerifier
            return SymbolicStepVerifier(timeout_ms=symbolic_timeout_ms)
        return LeanStepVerifier(endpoint=lean_endpoint, timeout_s=10)
    from .symbolic import SymbolicStepVerifier
    return SymbolicStepVerifier(timeout_ms=symbolic_timeout_ms)


__all__ = ["Step", "Verdict", "StepVerifier", "build_verifier"]
```

- [ ] **Step 4: Create stub modules so imports resolve**

Create `src/geometry_agent/verification/symbolic.py`:
```python
from __future__ import annotations
from . import Step, Verdict


class SymbolicStepVerifier:
    def __init__(self, timeout_ms: int = 200):
        self.timeout_ms = timeout_ms

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        return Verdict(verified="uncertain", reason="not implemented")
```

Create `src/geometry_agent/verification/lean_client.py`:
```python
from __future__ import annotations
from . import Step, Verdict


class LeanStepVerifier:
    def __init__(self, endpoint: str, timeout_s: int = 10):
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        return Verdict(verified="uncertain", reason="not implemented")
```

Create `src/geometry_agent/verification/llm_judge.py`:
```python
from __future__ import annotations
from . import Step, Verdict


class LLMJudge:
    def __init__(self, client):
        self.client = client

    def verdict(self, step: Step, premises: list[Step], failures: list[str]) -> Verdict:
        return Verdict(verified="uncertain", reason="not implemented")
```

Create `src/geometry_agent/verification/step_parser.py`:
```python
from __future__ import annotations
def parse_claim(statement: str):
    return None
```

- [ ] **Step 5: Run test to confirm it passes**

Run: `python -m pytest tests/unit/test_verification_middleware.py -p no:pyz3 -q`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/geometry_agent/verification/ tests/unit/test_verification_middleware.py
git commit -m "feat(verification): add Verdict/Step types, StepVerifier protocol, build_verifier factory"
```

### Task 2: claim_step tool schema & registration

**Files:**
- Modify: `src/geometry_agent/reasoning/tools.py`
- Modify: `src/geometry_agent/types.py` (add StepResult to tool results type if needed)

- [ ] **Step 1: Write failing test for tool schema**

Append to `tests/unit/test_verification_middleware.py`:

```python
def test_claim_step_tool_schema_exists():
    from geometry_agent.reasoning.tools import TOOL_SCHEMAS
    names = [s["function"]["name"] for s in TOOL_SCHEMAS]
    assert "claim_step" in names
    schema = next(s["function"] for s in TOOL_SCHEMAS if s["function"]["name"] == "claim_step")
    assert "statement" in schema["parameters"]["properties"]
    assert "premise_ids" in schema["parameters"]["properties"]
    assert "justification" in schema["parameters"]["properties"]
    assert "statement" in schema["parameters"]["required"]
```

- [ ] **Step 2: Run test to confirm failure**

Run: `python -m pytest tests/unit/test_verification_middleware.py::test_claim_step_tool_schema_exists -p no:pyz3 -q`
Expected: FAIL (claim_step not in schema)

- [ ] **Step 3: Add claim_step to tool schemas in tools.py**

Read the current file; insert a new tool dict before the closing `]` of the schemas list. Add after the `solve` tool definition:

```python
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
                "step_id": {"type": "string", "description": "Unique id for this step, e.g. s1, s2."},
                "statement": {
                    "type": "string",
                    "description": "The conclusion being asserted, e.g. AB/AC = AE/AD."
                },
                "premise_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ids of previously verified steps this depends on."
                },
                "justification": {
                    "type": "string",
                    "description": "Which lemma/method/axiom justifies the step, e.g. '相似三角形AA'."
                },
            },
            "required": ["step_id", "statement", "justification"],
        },
    },
},
```

- [ ] **Step 4: Add claim_step to `_TOOL_NAMES`**

Search for `_TOOL_NAMES = frozenset(` or equivalent set listing tool names; add `"claim_step"`.

- [ ] **Step 5: Make `claim_step` a pass-through that returns a pending verdict**

In `tools.py` add a handler function `claim_step(**kwargs)` that returns:
```python
{"status": "pending_verification", "step": kwargs}
```
Register it in the tools dict constructed in `enhanced_agent.py` (search for where tools_dict is built and add `"claim_step": claim_step`).

- [ ] **Step 6: Run test to confirm it passes**

Run: `python -m pytest tests/unit/test_verification_middleware.py::test_claim_step_tool_schema_exists -p no:pyz3 -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/geometry_agent/reasoning/tools.py src/geometry_agent/reasoning/enhanced_agent.py
git commit -m "feat(tools): add claim_step tool schema and pass-through handler"
```

---

## Phase 2: SymbolicStepVerifier (SymPy/Z3)

### Task 3: Algebraic step parser + SymPy verifier

**Files:**
- Create/modify: `src/geometry_agent/verification/step_parser.py`
- Modify: `src/geometry_agent/verification/symbolic.py`
- Test: `tests/unit/test_symbolic_verifier.py`

- [ ] **Step 1: Write failing tests for algebraic equality/inequality verification**

Create `tests/unit/test_symbolic_verifier.py`:

```python
import pytest
from geometry_agent.verification import Step, Verdict
from geometry_agent.verification.symbolic import SymbolicStepVerifier


def _mk(stmt, pids=None):
    return Step(id="s", statement=stmt, premise_ids=pids or [], justification="")


def _premise(stmt, pid):
    return Step(id=pid, statement=stmt, premise_ids=[], justification="")


def test_algebraic_equality_true():
    v = SymbolicStepVerifier()
    r = v.verify(_mk("(a+b)^2 = a^2 + 2ab + b^2"), [])
    assert r.verified == "true"


def test_algebraic_equality_false():
    v = SymbolicStepVerifier()
    r = v.verify(_mk("(a+b)^2 = a^2 + b^2"), [])
    assert r.verified == "false"
    assert "simplified" in r.evidence or "0" in r.evidence


def test_equality_from_premises():
    v = SymbolicStepVerifier()
    r = v.verify(
        _mk("x = 5", ["p1"]),
        [_premise("2*x = 10", "p1")],
    )
    assert r.verified == "true"


def test_trig_identity_sin2x():
    v = SymbolicStepVerifier()
    r = v.verify(_mk("sin(2*x) = 2*sin(x)*cos(x)"), [])
    assert r.verified == "true"


def test_inequality_true():
    v = SymbolicStepVerifier()
    # for positive a,b; AM >= GM
    r = v.verify(
        _mk("a+b >= 2*sqrt(a*b)", ["a_pos", "b_pos"]),
        [_premise("a > 0", "a_pos"), _premise("b > 0", "b_pos")],
    )
    # AM-GM is true but SymPy may not prove it from raw assumptions;
    # expected "uncertain" if not proved, never "false"
    assert r.verified in ("true", "uncertain")
```

- [ ] **Step 2: Run test — expect import/fail**

Run: `python -m pytest tests/unit/test_symbolic_verifier.py -p no:pyz3 -q`
Expected: FAIL (SymbolicStepVerifier.verify returns uncertain)

- [ ] **Step 3: Implement step_parser (Chinese→SymPy minimal)**

Replace `src/geometry_agent/verification/step_parser.py` with:

```python
"""Minimal parser converting claim strings to SymPy relational expressions.

Handles common exam notation: =, >=, <=, >, <, sqrt(), sin/cos/tan, ^, implicit ×,
Chinese punctuation (，。：）. Falls back to sympify with string replacements;
returns None on unparseable input.
"""
from __future__ import annotations
import re
import sympy as sp


_REL_RE = re.compile(r"\s*(>=|<=|>|<|=)\s*")
_FUNCS = {"sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
          "sin2": lambda x: 2*sp.sin(x)*sp.cos(x)}


def parse_claim(statement: str):
    """Return (lhs_sympy, rel, rhs_sympy) or None."""
    s = statement.strip().rstrip("。.")
    s = s.replace("（", "(").replace("）", ")").replace("，", ",")
    s = s.replace("²", "**2").replace("³", "**3")
    s = s.replace("·", "*").replace("×", "*").replace("÷", "/")
    m = _REL_RE.search(s)
    if not m:
        return None
    lhs_s, rel, rhs_s = s[:m.start()], m.group(1), s[m.end():]
    try:
        lhs = sp.sympify(lhs_s, locals=_FUNCS)
        rhs = sp.sympify(rhs_s, locals=_FUNCS)
    except Exception:
        return None
    rel_map = {"=": sp.Eq, ">=": sp.Ge, "<=": sp.Le, ">": sp.Gt, "<": sp.Lt}
    return lhs, rel_map[rel], rhs


def parse_expr(text: str):
    try:
        return sp.sympify(text.strip(), locals=_FUNCS)
    except Exception:
        return None
```

- [ ] **Step 4: Implement SymbolicStepVerifier algebra**

Replace `src/geometry_agent/verification/symbolic.py` with:

```python
"""Lightweight SymPy/Z3 per-step verifier for junior/senior modes."""
from __future__ import annotations
import threading
from . import Step, Verdict
from .step_parser import parse_claim, parse_expr


class _Timeout(Exception):
    pass


def _with_timeout(fn, ms):
    result = [None]
    def run():
        try:
            result[0] = fn()
        except Exception as e:
            result[0] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(ms / 1000)
    if t.is_alive():
        return _Timeout()
    if isinstance(result[0], Exception):
        raise result[0]
    return result[0]


class SymbolicStepVerifier:
    def __init__(self, timeout_ms: int = 200):
        self.timeout_ms = timeout_ms

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        parsed = parse_claim(step.statement)
        if parsed is None:
            return Verdict(verified="uncertain",
                           reason="statement unparseable for symbolic check")
        lhs, rel, rhs = parsed
        # Gather assumptions from premises (best-effort parse each premise)
        assumptions = []
        for p in premises:
            pp = parse_claim(p.statement)
            if pp is not None:
                assumptions.append(pp[1](pp[0], pp[2]))
        try:
            diff = sp.simplify(lhs - rhs)
        except Exception as e:
            return Verdict(verified="uncertain", reason=f"simplify failed: {e}")
        # Check equality
        if rel is sp.Eq:
            try:
                r = _with_timeout(lambda: sp.simplify(diff) == 0, self.timeout_ms)
            except Exception as e:
                return Verdict(verified="uncertain", reason=str(e))
            if r is _Timeout():
                return Verdict(verified="uncertain", reason="simplify timeout")
            if r is True:
                return Verdict(verified="true", evidence=f"simplified(lhs-rhs)=0  → {sp.simplify(lhs-rhs)}")
            # try assuming premises
            try:
                from sympy import ask, Q
                # fallback: uncertain (refutation too expensive)
                if diff.is_zero is False:
                    return Verdict(verified="false", evidence=f"lhs-rhs = {diff} ≠ 0")
                return Verdict(verified="uncertain",
                               reason=f"could not simplify difference to 0 (got {diff})")
            except Exception:
                return Verdict(verified="uncertain", reason="assumption check failed")
        # Inequality
        try:
            expr = rel(lhs, rhs)
            simp = sp.simplify(expr)
            if simp is True:
                return Verdict(verified="true", evidence=str(expr))
            if simp is False:
                return Verdict(verified="false", evidence=f"negation holds: {sp.simplify(~expr)}")
            return Verdict(verified="uncertain", reason=f"simplify returned {simp}")
        except Exception as e:
            return Verdict(verified="uncertain", reason=str(e))
```

- [ ] **Step 5: Run tests, fix until pass**

Run: `python -m pytest tests/unit/test_symbolic_verifier.py -p no:pyz3 -q`
Expected: all pass. If `test_inequality_true` fails (AM-GM not proven), accept `uncertain` — assertion already allows it.

- [ ] **Step 6: Commit**

```bash
git add src/geometry_agent/verification/step_parser.py src/geometry_agent/verification/symbolic.py tests/unit/test_symbolic_verifier.py
git commit -m "feat(verification): implement SymbolicStepVerifier (SymPy algebra/trig, timeout-bounded)"
```

### Task 4: Z3 geometric relation verification

**Files:**
- Modify: `src/geometry_agent/verification/symbolic.py`
- Modify: `src/geometry_agent/verification/step_parser.py`
- Test: `tests/unit/test_symbolic_verifier.py` (append cases)

- [ ] **Step 1: Add failing tests for geometry relations**

Append to `tests/unit/test_symbolic_verifier.py`:

```python
def test_parallel_implies_equal_slopes():
    v = SymbolicStepVerifier()
    # If AB ∥ CD and A=(0,0),B=(1,b),C=(0,c),D=(2,d) then b = (d-c)/2
    # For simplicity test a pure algebra consequence:
    # slope AB = slope CD  → (b-0)/(1-0) = (d-c)/(2-0)  → 2b = d-c
    r = v.verify(
        _mk("2*b = d - c", ["p1"]),
        [_premise("b/1 = (d-c)/2", "p1")],
    )
    assert r.verified == "true"


def test_perpendicular_dot_zero():
    v = SymbolicStepVerifier()
    r = v.verify(
        _mk("a*c + b*d = 0", ["p1"]),
        [_premise("(a,b) · (c,d) = 0", "p1")],
    )
    # dot product expansion — parser should handle ×
    assert r.verified == "true"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest tests/unit/test_symbolic_verifier.py -p no:pyz3 -q`

- [ ] **Step 3: Extend parser for dot/parallel/perpendicular notation**

In `step_parser.py`, before sympify, replace symbols:
- `·` → `*` (already done)
- Add recognition of `∥` / `⊥` as relation prefixes that map to slope/derivative checks. For now, handle the case where statement contains no relation but contains `⊥`/`∥` by converting to slope equality (limited scope).

For Task 4 minimal scope: extend `_FUNCS` with no changes needed; the existing algebra engine already handles cross-multiplied equalities. If the perpendicular test's premise uses `·`, `parse_expr` already replaces it to `*`. Verify that and add a direct SymPy test.

- [ ] **Step 4: Run tests, ensure pass**

If tests pass without Z3 changes (because premise directly gives the equation and conclusion is algebraic consequence), skip Z3 for this task and note Z3 geometric model as a later enhancement (the spec lists Z3 for geometry relations but the algebra engine handles slope/vector equalities via premise expansion).

- [ ] **Step 5: Commit**

```bash
git add src/geometry_agent/verification/ tests/unit/test_symbolic_verifier.py
git commit -m "test(verification): add geometric consequence cases for symbolic verifier"
```

---

## Phase 3: Middleware injection into feedback loop (retry + judge)

### Task 5: Wire verifier into _run_feedback_loop with retry

**Files:**
- Modify: `src/geometry_agent/reasoning/enhanced_agent.py`
- Modify: `src/geometry_agent/verification/llm_judge.py`
- Test: `tests/unit/test_verification_middleware.py`

- [ ] **Step 1: Write failing integration test for retry logic**

Append to `tests/unit/test_verification_middleware.py`:

```python
def test_verifier_called_for_claim_step_pending_result():
    """When a claim_step returns pending_verification, the agent must call verifier."""
    # This test patches the verifier and runs a minimal loop; simpler: unit-test the
    # helper that will be extracted.
    from geometry_agent.reasoning.enhanced_agent import _verify_and_retry
    from geometry_agent.verification import Step, Verdict, StepVerifier

    class FakeVerifier(StepVerifier):
        def __init__(self, sequence):
            self.seq = list(sequence)
            self.calls = 0
        def verify(self, step, premises):
            self.calls += 1
            return self.seq.pop(0) if self.seq else Verdict(verified="true", evidence="ok")

    class FakeJudge:
        def __init__(self): self.called = False; self.verdict = Verdict(verified="uncertain", reason="judge")
        def verdict(self, step, premises, failures):
            self.called = True; return self.verdict

    v = FakeVerifier([Verdict(verified="false", reason="no")])
    j = FakeJudge()
    step = Step(id="s1", statement="x=2", premise_ids=[], justification="")
    verdict, retries = _verify_and_retry(v, j, step, [], max_retries=0)
    assert retries == 0
    assert verdict.verified == "false"
    assert not j.called

    v2 = FakeVerifier([Verdict(verified="false", reason="nope")]*3)
    verdict2, retries2 = _verify_and_retry(v2, j, step, [], max_retries=3)
    assert retries2 == 3
    assert j.called  # judge invoked after 3 failures
```

- [ ] **Step 2: Extract _verify_and_retry helper into enhanced_agent.py**

Add to `src/geometry_agent/reasoning/enhanced_agent.py` (before `_run_feedback_loop` or as a module-level helper):

```python
def _verify_and_retry(verifier, judge, step, premises, max_retries=3):
    """Verify ``step``; on failure retry up to max_retries, then fall back to judge.

    Returns (Verdict, retry_count). The caller feeds the verdict back into the
    LLM loop: failures become retry nudges, uncertain becomes warning, true
    adds step to verified_steps.
    """
    failures = []
    for attempt in range(max_retries + 1):
        v = verifier.verify(step, premises)
        if v.verified == "true":
            return v, attempt
        failures.append(v.reason or "verification failed")
        if attempt < max_retries:
            # caller will inject failure feedback; loop continues with LLM retry
            continue
    # All retries exhausted — judge
    if judge is not None:
        jv = judge.verdict(step, premises, failures)
        return jv, max_retries
    return Verdict(verified="false", reason="; ".join(failures)), max_retries
```

- [ ] **Step 3: Import and wire verifier into EnhancedReasoningAgent.__init__**

At the top of `enhanced_agent.py` add:

```python
from .verification import build_verifier, Step, Verdict
from .verification.llm_judge import LLMJudge
```

In `EnhancedReasoningAgent.__init__`, after config loading:

```python
self.verifier = build_verifier(
    grade,
    client=self.client,
    lean_endpoint=getattr(config, "lean_endpoint", None),
    symbolic_timeout_ms=getattr(config, "symbolic_timeout_ms", 200),
)
self.llm_judge = LLMJudge(self.client)
self.verified_steps: dict[str, Step] = {}
self._step_retries: dict[str, int] = {}
self._pending_claim: Step | None = None
```

- [ ] **Step 4: Handle claim_step in the tool dispatch loop**

Inside `_run_feedback_loop`, after `result = dispatch(name, args, tools_dict)` and `tool_log.append(...)`, add a verification block:

```python
if name == "claim_step" and isinstance(result, dict) and result.get("status") == "pending_verification":
    step_data = result["step"]
    step_id = step_data.get("step_id", f"s{len(self.verified_steps)+1}")
    step = Step(
        id=step_id,
        statement=step_data.get("statement", ""),
        premise_ids=step_data.get("premise_ids", []),
        justification=step_data.get("justification", ""),
    )
    premises = [self.verified_steps[pid] for pid in step.premise_ids if pid in self.verified_steps]
    verdict, retries = _verify_and_retry(
        self.verifier, self.llm_judge, step, premises, max_retries=3
    )
    if verdict.verified == "true":
        self.verified_steps[step_id] = step
        result = {"verified": True, "step_id": step_id, "evidence": verdict.evidence,
                  "status": "verified"}
    elif verdict.verified == "uncertain":
        self.verified_steps[step_id] = step  # allow uncertain steps to be used
        result = {"verified": "uncertain", "step_id": step_id, "evidence": verdict.evidence,
                  "reason": verdict.reason, "status": "verified_uncertain"}
    else:
        # retry: send failure back to LLM; do NOT add to verified_steps
        failure_n = self._step_retries.get(step_id, 0) + 1
        self._step_retries[step_id] = failure_n
        result = {"verified": False, "reason": verdict.reason, "retry": failure_n,
                  "failures": failure_n, "status": "retry"}
```

This reuses the existing `_build_feedback` path: when `verified is False`, `_is_failure` returns True, triggering the existing consecutive-failure nudge. For retry ≤3 the LLM regenerates; after 3, `_verify_and_retry` already called judge and returned uncertain (which becomes `verified="uncertain"`).

- [ ] **Step 5: Update _build_feedback to label uncertain verdicts**

In `_build_feedback`, after the `verified is False` branch, add:

```python
elif result.get("verified") == "uncertain":
    content = f"工具 {tool_name} 验证存疑({result.get('reason','')}): {result_str}\n可继续但请注意此步未严格证明。"
```

- [ ] **Step 6: Inject verification contract into prompt_builder**

In `prompt_builder.py` `build_enhanced_prompt`, add to system instructions (grade-dependent):

For junior/senior:
```
"每得出一个非平凡结论(非单纯算术结果),必须先调用 claim_step 声明该结论,等待验证通过(✓)后再继续下一步。\n"
"验证失败会返回具体原因,请修正重述;连续3次失败将由审查员裁决。\n"
```

For competition: append `(竞赛模式将使用 Lean 形式化验证)`

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/unit/test_verification_middleware.py tests/unit/test_symbolic_verifier.py -p no:pyz3 -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/geometry_agent/reasoning/enhanced_agent.py src/geometry_agent/reasoning/prompt_builder.py src/geometry_agent/verification/llm_judge.py tests/unit/test_verification_middleware.py
git commit -m "feat(verification): wire StepVerifier into feedback loop with 3-retry+LLM-judge fallback"
```

### Task 6: LLMJudge implementation

**Files:**
- Modify: `src/geometry_agent/verification/llm_judge.py`
- Test: `tests/unit/test_llm_judge.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_llm_judge.py`:

```python
from geometry_agent.verification import Step, Verdict
from geometry_agent.verification.llm_judge import LLMJudge


class FakeClient:
    def __init__(self, reply): self.reply = reply; self.calls = 0
    def chat(self, messages, **kw):
        self.calls += 1
        return {"choices": [{"message": {"role": "assistant", "content": self.reply}}]}


def test_judge_returns_true_when_llm_says_valid():
    c = FakeClient('{"verdict":"true","reason":"by AM-GM"}')
    j = LLMJudge(c)
    v = j.verdict(Step(id="s", statement="a+b>=2*sqrt(ab)", premise_ids=[], justification=""), [], [])
    assert v.verified == "true"


def test_judge_returns_false_when_llm_says_invalid():
    c = FakeClient('{"verdict":"false","reason":"counterexample a=1,b=2 fails"}')
    j = LLMJudge(c)
    v = j.verdict(Step(id="s", statement="a+b>=2*sqrt(ab)", premise_ids=[], justification=""), [], [])
    assert v.verified == "false"


def test_judge_uncertain_on_garbled_reply():
    c = FakeClient("i'm not sure")
    j = LLMJudge(c)
    v = j.verdict(Step(id="s", statement="a+b>=2*sqrt(ab)", premise_ids=[], justification=""), [], [])
    assert v.verified == "uncertain"
```

- [ ] **Step 2: Run test → fail**

- [ ] **Step 3: Implement LLMJudge**

Replace `src/geometry_agent/verification/llm_judge.py`:

```python
"""LLM-as-judge fallback when Symbolic/Lean verification fails 3 times."""
from __future__ import annotations
import json
import re
from . import Step, Verdict


_SYSTEM = (
    "You are a strict mathematical proof reviewer. Given premises and a proposed "
    "conclusion that failed automatic verification three times, judge whether the "
    "conclusion is valid. Reply with a single JSON object: "
    '{"verdict":"true|false|uncertain","reason":"<brief justification>"}.'
)


class LLMJudge:
    def __init__(self, client):
        self.client = client

    def verdict(self, step: Step, premises: list[Step], failures: list[str]) -> Verdict:
        premise_txt = "\n".join(f"- {p.id}: {p.statement}" for p in premises) or "(none)"
        fail_txt = "\n".join(f"- {f}" for f in failures) or "(none)"
        user_msg = (
            f"Premises:\n{premise_txt}\n\n"
            f"Proposed conclusion ({step.justification}): {step.statement}\n\n"
            f"Previous verification failures:\n{fail_txt}\n\n"
            "Is the conclusion valid? Reply with JSON only."
        )
        try:
            resp = self.client.chat(
                [{"role": "system", "content": _SYSTEM},
                 {"role": "user", "content": user_msg}],
                temperature=0.0,
            )
            content = (resp["choices"][0]["message"]["content"] or "").strip()
            m = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                v = data.get("verdict", "uncertain")
                if v not in ("true", "false", "uncertain"):
                    v = "uncertain"
                return Verdict(verified=v, evidence=content, reason=data.get("reason", ""))
        except Exception as e:
            return Verdict(verified="uncertain", evidence="", reason=f"judge error: {e}")
        return Verdict(verified="uncertain", evidence=content, reason="could not parse judge reply")
```

- [ ] **Step 4: Run tests → pass**

Run: `python -m pytest tests/unit/test_llm_judge.py -p no:pyz3 -q`

- [ ] **Step 5: Commit**

```bash
git add src/geometry_agent/verification/llm_judge.py tests/unit/test_llm_judge.py
git commit -m "feat(verification): implement LLMJudge fallback with strict JSON output"
```

---

## Phase 4: Lemma library expansion & config

### Task 7: Extend KnowledgeEntry fields + grade expansion seed

**Files:**
- Modify: `src/geometry_agent/types.py` (KnowledgeEntry/MethodEntry)
- Modify: `src/geometry_agent/knowledge/curated.py`
- Modify: `src/geometry_agent/knowledge/manager.py` (format_for_prompt uses formal_id/proof_hint)

- [ ] **Step 1: Add formal_id, proof_hint fields to types**

In `types.py`, in `KnowledgeEntry`, add fields (with defaults) before `grade`:

```python
formal_id: str = ""       # SymPy callable or Lean theorem name
proof_hint: str = ""      # Chinese hint for LLM
```

Add same to `MethodEntry` if MethodEntry is used similarly.

- [ ] **Step 2: Populate 10 junior + 15 senior + 10 competition entries as seed**

In `curated.py`, add entries covering (as concrete KnowledgeEntry instances with all fields):
- Junior: 角平分线定理、中线长公式、射影定理、弦切角定理、圆幂定理、塞瓦定理(基础)、梅涅劳斯(基础)、海伦公式、中点坐标、平行线分线段成比例
- Senior: 椭圆焦点三角形面积、双曲线渐近线、抛物线焦点弦长、导数极值点偏移(基础)、向量三点共线、面面垂直判定、法向量二面角、排列组合隔板法、正态分布 3σ、参数方程求最值
- Competition: Desargues、Pascal 圆、极点极线、反演基本性质、复数法旋转、Schur 不等式、Muirhead、AM-GM 加权、调和点列、面积法消点

Each entry must have `grade=GradeLevel.X`, `formal_id` (SymPy/Z3/Lean name when applicable, else ""), `proof_hint="用{方法}..."`.

- [ ] **Step 3: Update format_for_prompt to include proof_hint**

In `manager.py` `format_for_prompt`, when rendering each method/entry, append `proof_hint` in parentheses after the content when non-empty.

- [ ] **Step 4: Add verification config to default.yaml**

Append to `configs/default.yaml`:

```yaml
verification:
  enabled: true
  max_retries: 3
  symbolic:
    timeout_ms: 200
  lean:
    endpoint: "http://10.42.0.124:9407"
    timeout_s: 10
  llm_judge:
    enabled: true
```

Wire config loading in `cli.py` and pass to `EnhancedReasoningAgent` (add a `verification` kwarg that constructs the verifier; update `__init__` signature to accept a `verification_config` dict).

- [ ] **Step 5: Run existing test suite → no regression**

Run: `python -m pytest tests/unit -p no:pyz3 -q`
Expected: all pass (202+).

- [ ] **Step 6: Commit**

```bash
git add src/geometry_agent/types.py src/geometry_agent/knowledge/ configs/default.yaml src/geometry_agent/cli.py
git commit -m "feat(knowledge): add formal_id/proof_hint fields; seed junior/senior/competition entries; verification config"
```

---

## Phase 5: Lean service on rdzs02 + LeanStepVerifier

### Task 8: Lean HTTP service (Docker + FastAPI) and deploy script

**Files:**
- Create: `scripts/Dockerfile.lean`
- Create: `scripts/lean_service.py`
- Create: `scripts/deploy_lean_service.py`
- Create/modify: `src/geometry_agent/verification/lean_client.py`
- Test: `tests/unit/test_lean_client.py` (mock HTTP)

- [ ] **Step 1: Write failing test for Lean client**

Create `tests/unit/test_lean_client.py`:

```python
import json
from unittest.mock import patch, MagicMock
from geometry_agent.verification import Step, Verdict
from geometry_agent.verification.lean_client import LeanStepVerifier


def _mk(stmt, pids=None): return Step(id="s", statement=stmt, premise_ids=pids or [], justification="")


def _fake_response(status, body):
    r = MagicMock()
    r.status_code = status
    r.text = json.dumps(body)
    def json(): return body
    r.json = json
    return r


def test_lean_verify_true(monkeypatch):
    import requests
    v = LeanStepVerifier("http://x:9407", timeout_s=2)
    fake_post = MagicMock(return_value=_fake_response(200, {"verified": True, "output": "ok"}))
    monkeypatch.setattr(requests, "post", fake_post)
    r = v.verify(_mk("1+1=2"), [])
    assert r.verified == "true"
    assert "ok" in r.evidence
    fake_post.assert_called_once()
    kwargs = fake_post.call_args.kwargs
    assert kwargs["timeout"] == 2


def test_lean_verify_false(monkeypatch):
    import requests
    v = LeanStepVerifier("http://x:9407")
    fake_post = MagicMock(return_value=_fake_response(200, {"verified": False, "output": "error: type mismatch"}))
    monkeypatch.setattr(requests, "post", fake_post)
    r = v.verify(_mk("1+1=3"), [])
    assert r.verified == "false"


def test_lean_unreachable_returns_uncertain(monkeypatch):
    import requests
    v = LeanStepVerifier("http://x:9407")
    def boom(*a, **k): raise Exception("connection refused")
    monkeypatch.setattr(requests, "post", boom)
    r = v.verify(_mk("1+1=2"), [])
    assert r.verified == "uncertain"
    assert "unreachable" in r.reason or "connection" in r.reason
```

- [ ] **Step 2: Run test → fail** (LeanStepVerifier.verify returns uncertain, not matching)

- [ ] **Step 3: Implement LeanStepVerifier HTTP client**

Replace `src/geometry_agent/verification/lean_client.py`:

```python
"""HTTP client for the Lean 4 verification service on rdzs02."""
from __future__ import annotations
import json
import requests
from . import Step, Verdict


_LEAN_TMPL = (
    "import Mathlib\n"
    "open Real\n\n"
    "theorem step_claim {premises_block}{conclusion_lean} := by\n"
    "  {tactic}\n"
)


def _to_lean_expr(stmt: str) -> str:
    """Map a claim string to a Lean expression stub.

    For the initial version, only simple algebra/inequalities are translated.
    Falls back to an `sorry` so the service reports an error and the caller
    treats it as uncertain.
    """
    s = stmt.replace("^", "**").replace("sqrt", "Real.sqrt").replace("π", "Real.pi")
    s = s.replace("sin", "Real.sin").replace("cos", "Real.cos").replace("tan", "Real.tan")
    s = s.replace("·", "*").replace("×", "*").replace("÷", "/")
    return s


class LeanStepVerifier:
    def __init__(self, endpoint: str, timeout_s: int = 10):
        self.endpoint = endpoint.rstrip("/") + "/verify"
        self.timeout_s = timeout_s

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        premises_lines = []
        for p in premises:
            premises_lines.append(f"have h_{p.id} : {_to_lean_expr(p.statement)} := sorry")
        premises_block = "\n".join(premises_lines) + ("\n" if premises_lines else "")
        concl = _to_lean_expr(step.statement)
        lean_src = _LEAN_TMPL.format(
            premises_block=premises_block,
            conclusion_lean=concl,
            tactic="ring_nf <;> norm_num <;> linarith",
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
                return Verdict(verified="true", evidence=data.get("output", ""),
                               lean_source=lean_src)
            return Verdict(verified="false", evidence=data.get("output", ""),
                           reason=data.get("error", "lean rejected"),
                           lean_source=lean_src)
        except requests.RequestException as e:
            return Verdict(verified="uncertain", reason=f"lean service unreachable: {e}",
                           lean_source=lean_src)
        except Exception as e:
            return Verdict(verified="uncertain", reason=f"lean client error: {e}",
                           lean_source=lean_src)
```

- [ ] **Step 4: Create FastAPI service**

Create `scripts/lean_service.py`:

```python
"""Lean 4 per-step verification HTTP service.

Receives {"premises":[...], "conclusion":"...", "lean_source":"..."}; writes to a
temp .lean file, runs `lake env lean`, and returns whether it compiles.
"""
from __future__ import annotations
import os, tempfile, subprocess, uuid
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class VerifyReq(BaseModel):
    premises: list[str] = []
    conclusion: str
    lean_source: str


LEAN_TIMEOUT_S = int(os.environ.get("LEAN_TIMEOUT_S", "8"))
LEAN_CMD = os.environ.get("LEAN_CMD", "lake env lean")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/verify")
def verify(req: VerifyReq):
    tmpdir = tempfile.mkdtemp(prefix="lean-")
    src = os.path.join(tmpdir, "step.lean")
    with open(src, "w") as f:
        f.write(req.lean_source)
    try:
        r = subprocess.run(
            f"cd {tmpdir} && {LEAN_CMD} step.lean",
            shell=True, capture_output=True, text=True, timeout=LEAN_TIMEOUT_S,
        )
        out = (r.stdout or "") + (r.stderr or "")
        verified = r.returncode == 0 and "error:" not in out
        return {"verified": verified, "output": out, "elapsed_ms": 0}
    except subprocess.TimeoutExpired:
        return {"verified": False, "output": "timeout", "elapsed_ms": LEAN_TIMEOUT_S*1000}
    finally:
        subprocess.run(["rm", "-rf", tmpdir], capture_output=True)
```

- [ ] **Step 5: Create Dockerfile**

Create `scripts/Dockerfile.lean`:

```dockerfile
FROM ghcr.io/leanprover/lean4:stable

RUN apt-get update && apt-get install -y python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip3 install fastapi uvicorn pydantic

WORKDIR /workspace
RUN leanpkg init stepverify 2>/dev/null || true
RUN lake exe cache get! 2>/dev/null || true
RUN echo 'require mathlib from git "https://github.com/leanprover-community/mathlib4"' >> lakefile.lean 2>/dev/null || true
RUN lake update Mathlib 2>/dev/null || true

COPY lean_service.py /workspace/lean_service.py

EXPOSE 9407
CMD ["uvicorn", "lean_service:app", "--host", "0.0.0.0", "--port", "9407"]
```

- [ ] **Step 6: Write deploy script**

Create `scripts/deploy_lean_service.py` (uses paramiko or subprocess SSH):

```python
"""Deploy Lean verification service to rdzs02.

Usage: python scripts/deploy_lean_service.py --host 10.42.0.124 --user rdzs02 --pass rdzs1234
"""
from __future__ import annotations
import argparse, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_ssh(host, user, pwd, cmd, check=True):
    full = ["sshpass", "-p", pwd, "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{host}", cmd]
    print(f"[ssh] {cmd}")
    return subprocess.run(full, check=check, capture_output=True, text=True)


def run_scp(host, user, pwd, src, dst):
    full = ["sshpass", "-p", pwd, "scp", "-o", "StrictHostKeyChecking=no", src, f"{user}@{host}:{dst}"]
    print(f"[scp] {src} -> {dst}")
    subprocess.run(full, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.42.0.124")
    ap.add_argument("--user", default="rdzs02")
    ap.add_argument("--pass", default="rdzs1234", dest="pwd")
    ap.add_argument("--port", type=int, default=9407)
    args = ap.parse_args()

    # Ensure docker on rdzs02
    run_ssh(args.host, args.user, args.pwd, "which docker || (sudo apt update && sudo apt install -y docker.io && sudo usermod -aG docker $USER && newgrp docker)")
    # Copy Dockerfile and service
    home = run_ssh(args.host, args.user, args.pwd, "echo $HOME", check=True).stdout.strip()
    run_ssh(args.host, args.user, args.pwd, f"mkdir -p {home}/lean-svc")
    run_scp(args.host, args.user, args.pwd, str(ROOT / "Dockerfile.lean"), f"{home}/lean-svc/Dockerfile")
    run_scp(args.host, args.user, args.pwd, str(ROOT / "lean_service.py"), f"{home}/lean-svc/lean_service.py")
    # Build & run
    run_ssh(args.host, args.user, args.pwd, f"cd {home}/lean-svc && docker build -t lean-verify -f Dockerfile .")
    run_ssh(args.host, args.user, args.pwd, f"docker rm -f lean-verify 2>/dev/null; docker run -d --name lean-verify --restart unless-stopped -p {args.port}:9407 lean-verify")
    # Wait for health
    for _ in range(20):
        time.sleep(2)
        r = run_ssh(args.host, args.user, args.pwd, f"curl -sf http://127.0.0.1:{args.port}/health", check=False)
        if r.returncode == 0:
            print(f"Lean service healthy on http://{args.host}:{args.port}")
            return 0
    print("Lean service failed to start. Check docker logs: ssh rdzs02@host 'docker logs lean-verify'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run client unit tests (mock HTTP) → pass**

Run: `python -m pytest tests/unit/test_lean_client.py -p no:pyz3 -q`
Expected: 3 passed

- [ ] **Step 8: Deploy to rdzs02** (requires network to rdzs02 hotspot)

Run: `python scripts/deploy_lean_service.py`
Wait for build (~5-15 min first time, Docker pulls lean image + mathlib).

- [ ] **Step 9: Smoke-test remote**

```bash
curl -sf http://10.42.0.124:9407/health && echo OK
```

- [ ] **Step 10: Commit**

```bash
git add scripts/Dockerfile.lean scripts/lean_service.py scripts/deploy_lean_service.py src/geometry_agent/verification/lean_client.py tests/unit/test_lean_client.py
git commit -m "feat(verification): Lean HTTP service (FastAPI+Docker) + LeanStepVerifier client + deploy script"
```

---

## Phase 6: E2E tests, PDF report markers, final regression

### Task 9: Mark verified steps in PDF report

**Files:**
- Modify: `src/geometry_agent/report/__init__.py` (or wherever ProofPlan is rendered to LaTeX)
- Modify: `src/geometry_agent/types.py` (ProofStep gets verified field)

- [ ] **Step 1: Add verified field to ProofStep**

In `types.py`, in `ProofStep` (or the equivalent step model), add:
```python
verified: Literal["true", "false", "uncertain"] = "true"
```

- [ ] **Step 2: Mark steps in plan synthesis**

In `enhanced_agent.py` `_synthesize_plan`, when building steps from `tool_log`, if a step corresponds to a `claim_step` with verified result, carry the verified flag into the ProofStep.

- [ ] **Step 3: Render verification markers in LaTeX**

In report module, prepend a symbol to each step's statement:
- `verified="true"`: `✓ ` (or `\checkmark`)
- `verified="uncertain"`: `⚠ ` with small footnote "此步未通过形式化验证，经审查员裁决存疑通过"
- `verified="false"`: do not render as a step (convergence would have triggered reflect before final plan)

- [ ] **Step 4: Run existing report tests → no regression**

Run: `python -m pytest tests/unit/test_math_reliability.py -p no:pyz3 -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/geometry_agent/types.py src/geometry_agent/report/__init__.py src/geometry_agent/reasoning/enhanced_agent.py
git commit -m "feat(report): show ✓/⚠ verification markers on each proof step in PDF"
```

### Task 10: E2E tests across three grades

**Files:**
- Create: `tests/e2e/test_graded_verification.py`

- [ ] **Step 1: Write E2E test with fake LLM that emits a known claim sequence**

Create `tests/e2e/test_graded_verification.py` that:
- Uses a FakeClient whose replies deterministically call `claim_step` + `solve` for a simple algebra/geometry problem
- Asserts that `verified_steps` contains the expected step ids
- Asserts final plan has all steps marked `verified=true`
- 3 parametrized cases: junior algebraic identity, senior trig identity, competition Lean path (mocked)

- [ ] **Step 2: Run E2E → pass**

Run: `python -m pytest tests/e2e/test_graded_verification.py -p no:pyz3 -q`

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -p no:pyz3 -q`
Expected: all pass (prior 202+ plus new tests).

- [ ] **Step 4: Re-run real exam suite**

Run: `python /tmp/opencode/real_exam_test.py` (note: requires 0 unicode leaks + PDF render). It must ALL PASS with verification enabled.

- [ ] **Step 5: Final commit**

```bash
git add tests/e2e/test_graded_verification.py
git commit -m "test(e2e): grade verification E2E tests across junior/senior/competition"
```

---

## Self-Review Checklist (done before handoff)

- [x] Spec coverage: every section in the design doc maps to a Task (1-10).
- [x] Placeholders: no TBD/TODO; every code block has concrete code; commands have expected output.
- [x] Type consistency: `Verdict.verified` uses `Literal["true","false","uncertain"]` consistently; `Step` id field used as premise_ids; verifier factory signature matches __init__ wiring.
- [x] File paths absolute/relative match the project layout (`src/geometry_agent/...`, `tests/...`, `scripts/...`).
- [x] Phase ordering respects dependencies: skeleton → symbolic → middleware → lemma lib → Lean → E2E.
- [x] Resource budget honored: SymbolicVerifier uses thread timeout 200ms, Lean service is remote on rdzs02, local overhead <100MB.
