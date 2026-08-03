"""Lean 4 per-step verification HTTP service.

Receives {"premises":[...], "conclusion":"...", "lean_source":"..."}; writes to a
temp .lean file, runs `lean` compiler, returns whether it compiles without errors.
This is intentionally minimal — no lake project, no mathlib dependency for the
initial version. A future version may add lake+mathlib; the API shape is forward-
compatible.
"""
from __future__ import annotations
import os, tempfile, subprocess, uuid
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class VerifyReq(BaseModel):
    premises: list[str] = []
    conclusion: str
    lean_source: str | None = None


LEAN_TIMEOUT_S = int(os.environ.get("LEAN_TIMEOUT_S", "8"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/verify")
def verify(req: VerifyReq):
    src = req.lean_source
    if src is None:
        src = (
            "theorem step_claim : " + req.conclusion + " := by\n"
            "  simp\n  <;> decide\n"
        )
    tmpdir = tempfile.mkdtemp(prefix="lean-")
    path = os.path.join(tmpdir, "step.lean")
    try:
        with open(path, "w") as f:
            f.write(src)
        r = subprocess.run(
            f"cd {tmpdir} && lean step.lean",
            shell=True, capture_output=True, text=True, timeout=LEAN_TIMEOUT_S,
        )
        out = (r.stdout or "") + (r.stderr or "")
        verified = r.returncode == 0 and "error:" not in out
        return {"verified": verified, "output": out, "elapsed_ms": 0}
    except subprocess.TimeoutExpired:
        return {"verified": False, "output": "timeout", "elapsed_ms": LEAN_TIMEOUT_S*1000}
    except Exception as e:
        return {"verified": False, "output": str(e), "elapsed_ms": 0}
    finally:
        subprocess.run(["rm", "-rf", tmpdir], capture_output=True)
