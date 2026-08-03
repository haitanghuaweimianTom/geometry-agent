"""Geometry Agent — FastAPI backend.

Run:
    uvicorn geometry_agent.api.server:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
    GET  /                  → web UI (static/index.html)
    GET  /api/health        → liveness probe
    POST /api/solve         → solve a single problem, returns PDF + steps
    POST /api/solve-multi   → solve a multi-part problem
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from geometry_agent.config import load_settings
from geometry_agent.human_loop.pdf_compiler import (
    multi_question_to_pdf,
    solution_to_pdf,
)
from geometry_agent.normalize import normalize_problem_text
from geometry_agent.pipeline import GeometryPipeline
from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
from geometry_agent.reasoning.experience import ExperienceMemory
from geometry_agent.types import GradeLevel

# Reuse the CLI helpers for answer extraction & numeric verification
import sys

_CLI = Path(__file__).resolve().parents[3] / "geometry_agent_cli.py"
if str(_CLI.parent) not in sys.path:
    sys.path.insert(0, str(_CLI.parent))
from geometry_agent_cli import _extract_answer, _numeric_verify_fixed_point  # type: ignore

# --------------------------------------------------------------------------- #
# App + settings
# --------------------------------------------------------------------------- #
_STATIC_DIR = Path(__file__).resolve().parents[3] / "static"

app = FastAPI(title="Geometry Agent API", version="0.1.0")


def _grade(s: str) -> GradeLevel:
    return {
        "junior": GradeLevel.JUNIOR,
        "senior": GradeLevel.SENIOR,
        "competition": GradeLevel.COMPETITION,
    }.get(s, GradeLevel.SENIOR)


def _settings(max_calls: int | None = None):
    s = load_settings("configs/default.yaml")
    s.human_loop.enabled = False
    if max_calls:
        s.llm.max_tool_calls = max_calls
    return s


def _solve_one(
    text: str,
    grade: GradeLevel,
    s,
    p: GeometryPipeline,
    tools: dict,
    max_calls: int,
) -> dict[str, Any]:
    """Run the reasoning loop with retry + numeric verification. Returns a dict."""
    t0 = time.time()
    sol = None
    retries = 0
    is_fixed_pt = "定点" in text or "过定点" in text or "恒过" in text
    for attempt in range(3):
        agent = EnhancedReasoningAgent(
            s.llm,
            tools={},
            knowledge_manager=p.knowledge_manager,
            grade=grade,
            experience_memory=ExperienceMemory(),
        )
        plan = agent.reason("", text, tools)
        sol = _extract_answer(plan)
        good = sol.confidence >= 0.5 and len(sol.proof) >= 2
        if good and is_fixed_pt:
            good = _numeric_verify_fixed_point(text, sol.answer, tools)
        if good:
            break
        if attempt < 2:
            retries += 1
    elapsed = time.time() - t0
    error = None
    if sol.confidence == 0.0 and not sol.proof:
        if getattr(agent.client, "is_offline", False):
            error = "LLM client is offline — no reasoning was performed"
        else:
            error = "Agent produced an empty proof plan"
    return {
        "solution": sol,
        "elapsed": elapsed,
        "retries": retries,
        "verified": bool(sol.verified),
        "error": error,
    }


def _solution_to_dict(sol) -> dict[str, Any]:
    return {
        "answer": sol.answer,
        "confidence": round(sol.confidence, 2),
        "verified": sol.verified,
        "steps": [
            {
                "step": st.step,
                "statement": st.statement,
                "reason": st.reason,
                "verified": st.verified,
            }
            for st in sol.proof
        ],
        "reasoning_summary": sol.reasoning_summary,
        "key_equations": list(sol.key_equations),
    }


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #
class SolveRequest(BaseModel):
    text: str
    grade: str = "senior"
    max_calls: int = 60


class SolveMultiRequest(BaseModel):
    text: str
    subs: list[str]
    grade: str = "senior"
    max_calls: int = 60


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "geometry-agent", "version": "0.1.0"}


@app.post("/api/solve")
def solve(req: SolveRequest):
    req.text = normalize_problem_text(req.text)
    if not req.text.strip():
        raise HTTPException(400, "题目文本不能为空")
    grade = _grade(req.grade)
    s = _settings(req.max_calls)
    p = GeometryPipeline(s)
    tools = p._tools(None) if hasattr(p, "_tools") else {}
    res = _solve_one(req.text, grade, s, p, tools, req.max_calls)
    sol = res["solution"]
    error = res.get("error")
    if error:
        return JSONResponse(
            {
                "ok": False,
                "error": error,
                "elapsed": round(res["elapsed"], 1),
                "retries": res["retries"],
            }
        )
    ts = int(time.time())
    pdf_name = f"outputs/solve_{ts}.pdf"
    pdf_path = solution_to_pdf(req.text, sol, None, pdf_name, "几何题解答报告")
    return JSONResponse(
        {
            "ok": True,
            "elapsed": round(res["elapsed"], 1),
            "retries": res["retries"],
            "pdf": f"/api/pdf/{Path(pdf_path).name}",
            "solution": _solution_to_dict(sol),
        }
    )


@app.post("/api/solve-multi")
def solve_multi(req: SolveMultiRequest):
    req.text = normalize_problem_text(req.text)
    if not req.text.strip():
        raise HTTPException(400, "题干不能为空")
    if not req.subs:
        raise HTTPException(400, "至少需要一个小题")
    grade = _grade(req.grade)
    s = _settings(req.max_calls)
    p = GeometryPipeline(s)
    tools = p._tools(None) if hasattr(p, "_tools") else {}
    results = []
    for i, sub_text in enumerate(req.subs):
        sub_text = normalize_problem_text(sub_text)
        full_text = req.text + " " + sub_text
        res = _solve_one(full_text, grade, s, p, tools, req.max_calls)
        error = res.get("error")
        if error:
            return JSONResponse(
                {
                    "ok": False,
                    "error": error,
                    "part": i + 1,
                }
            )
        sol = res["solution"]
        results.append(
            {
                "label": f"({i+1})",
                "question": sub_text,
                "solution_dict": _solution_to_dict(sol),
                "solution": sol,
            }
        )
    ts = int(time.time())
    pdf_name = f"outputs/multi_{ts}.pdf"
    subs_for_pdf = [
        {"label": r["label"], "question": r["question"], "solution": r["solution"]}
        for r in results
    ]
    pdf_path = multi_question_to_pdf(
        req.text, subs_for_pdf, None, pdf_name, "几何题解答报告"
    )
    return JSONResponse(
        {
            "ok": True,
            "pdf": f"/api/pdf/{Path(pdf_path).name}",
            "parts": [
                {
                    "label": r["label"],
                    "question": r["question"],
                    "solution": r["solution_dict"],
                }
                for r in results
            ],
        }
    )


@app.get("/api/pdf/{name}")
def get_pdf(name: str):
    # Prevent path traversal
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "非法文件名")
    p = Path("outputs") / name
    if not p.exists():
        raise HTTPException(404, "PDF 不存在")
    return FileResponse(str(p), media_type="application/pdf", filename=name)


# Serve the web UI
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
