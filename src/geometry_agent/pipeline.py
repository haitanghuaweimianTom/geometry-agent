"""End-to-end pipeline orchestration (see design/11-Engineering.md §4).

This module wires the modules together. Each module is imported lazily so the
package remains importable even before all implementations are filled in
(parallel development friendly).

Pipeline stages:
  parse -> build_graph -> extract_relations -> verify
  -> [HUMAN REVIEW CHECKPOINT: LaTeX+TikZ PDF preview, user corrections]
  -> to_dsl -> knowledge_retrieval -> reason(enhanced) -> solve
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .types import (
    Correction,
    GeometryGraph,
    SolveRequest,
    SolveResponse,
)
from .logging_util import log_step


class GeometryPipeline:
    """Orchestrates the full pipeline with human-in-the-loop review."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._parser = None
        self._graph_builder = None
        self._agent_scheduler = None
        self._verifier = None
        self._dsl_serializer = None
        self._dsl_parser = None
        self._llm_agent = None
        self._solver = None
        self._theorem_db = None
        self._knowledge_manager = None
        self._code_executor = None
        self._human_reviewer = None
        from .types import GradeLevel
        from .reasoning.experience import ExperienceMemory
        self._grade = GradeLevel.SENIOR
        self._experience_memory = ExperienceMemory()

    # ----- lazy module loaders -----
    @property
    def parser(self):
        if self._parser is None:
            from .perception.orchestrator import GeometryParser
            self._parser = GeometryParser(self.settings.parser)
        return self._parser

    @property
    def graph_builder(self):
        if self._graph_builder is None:
            from .graph.builder import GraphBuilder
            self._graph_builder = GraphBuilder(self.settings.graph)
        return self._graph_builder

    @property
    def agent_scheduler(self):
        if self._agent_scheduler is None:
            from .agents.scheduler import AgentScheduler
            self._agent_scheduler = AgentScheduler(self.settings.graph)
        return self._agent_scheduler

    @property
    def verifier(self):
        if self._verifier is None:
            from .verifier.engine import VerifierEngine
            self._verifier = VerifierEngine(self.settings.verifier)
        return self._verifier

    @property
    def dsl_serializer(self):
        if self._dsl_serializer is None:
            from .dsl.serializer import to_dsl
            self._dsl_serializer = to_dsl
        return self._dsl_serializer

    @property
    def llm_agent(self):
        # default grade = SENIOR; per-request override handled in run() via
        # _agent_for_grade() so different grades can coexist.
        if self._llm_agent is None:
            from .reasoning.enhanced_agent import EnhancedReasoningAgent
            self._llm_agent = EnhancedReasoningAgent(
                self.settings.llm,
                tools={},
                knowledge_manager=self.knowledge_manager,
                grade=self._grade,
            )
        return self._llm_agent

    def _agent_for_grade(self, grade):
        """Return an EnhancedReasoningAgent scoped to ``grade``.

        Agents are cached per grade so repeated calls reuse the instance.
        All agents share the same ExperienceMemory so lessons learned at one
        grade are available at others.
        """
        from .reasoning.enhanced_agent import EnhancedReasoningAgent
        if not hasattr(self, "_agents_by_grade"):
            self._agents_by_grade = {}
        if grade not in self._agents_by_grade:
            self._agents_by_grade[grade] = EnhancedReasoningAgent(
                self.settings.llm,
                tools={},
                knowledge_manager=self.knowledge_manager,
                grade=grade,
                experience_memory=self._experience_memory,
            )
        return self._agents_by_grade[grade]

    @property
    def solver(self):
        if self._solver is None:
            from .solver.engine import SymbolicSolver
            self._solver = SymbolicSolver(self.settings.solver)
        return self._solver

    @property
    def theorem_db(self):
        if self._theorem_db is None:
            from .theorems.db import TheoremDB
            self._theorem_db = TheoremDB(self.settings.solver.theorem_db_path)
        return self._theorem_db

    @property
    def knowledge_manager(self):
        if self._knowledge_manager is None:
            from .knowledge.manager import KnowledgeManager
            self._knowledge_manager = KnowledgeManager(self.settings.knowledge)
        return self._knowledge_manager

    @property
    def code_executor(self):
        if self._code_executor is None:
            from .tools.code_executor import CodeExecutor
            self._code_executor = CodeExecutor(self.settings.code_exec)
        return self._code_executor

    @property
    def human_reviewer(self):
        if self._human_reviewer is None:
            from .human_loop.reviewer import HumanReviewer
            self._human_reviewer = HumanReviewer(self.settings.human_loop)
        return self._human_reviewer

    # ----- DSL reference resolution -----
    def _resolve_ref(self, graph: GeometryGraph, ref: str) -> str:
        if not ref or not isinstance(ref, str):
            return ref
        ref = ref.strip()
        for n in graph.nodes:
            if n.id == ref:
                return n.id
        import re as _re
        m = _re.match(r"^(Point|Line|Segment|Ray|Circle|Arc|Ellipse|Polygon|Triangle)\(([^)]+)\)$", ref)
        if m:
            label = m.group(2).strip()
            for n in graph.nodes:
                if n.label == label:
                    return n.id
        for n in graph.nodes:
            if n.label == ref:
                return n.id
        return ref

    # ----- tools exposed to LLM -----
    def _tools(self, graph: GeometryGraph | None = None) -> dict[str, Any]:
        db = self.theorem_db
        g = graph
        ce = self.code_executor

        def _verify(rel, src, dst, attrs=None):
            if g is not None:
                src = self._resolve_ref(g, src)
                dst = self._resolve_ref(g, dst)
            return self.verifier.verify_one(rel, src, dst, attrs or {})

        def _execute_code(code):
            return ce.execute(code)

        def _complex_method(args):
            from .tools.geometry_prover import complex_method
            return complex_method(args)

        def _coordinate_method(args):
            from .tools.geometry_prover import coordinate_method
            return coordinate_method(args)

        return {
            "verify": _verify,
            "solve": lambda equations, goal=None: self.solver.solve_equations(equations, goal),
            "search": lambda query: [t.model_dump() for t in db.search(query, k=5)],
            "graph_query": lambda q: {},
            "execute_code": _execute_code,
            "complex_method": _complex_method,
            "coordinate_method": _coordinate_method,
        }

    # ----- main entry -----
    def run(
        self,
        request: SolveRequest,
        corrections: list[Correction] | None = None,
    ) -> SolveResponse:
        """Run the full pipeline.

        Args:
            request: problem image + text.
            corrections: optional pre-supplied human corrections to apply at the
                review checkpoint (non-interactive mode). When None and
                human_loop is enabled in interactive mode, prompts on stdin.
        """
        image_path = Path(request.image_path)

        # 1. Perception
        with log_step("pipeline", "parse", image=str(image_path)):
            primitives = self.parser.parse(image_path, request.problem_text)

        with log_step("pipeline", "build_graph"):
            graph = self.graph_builder.build(primitives)

        with log_step("pipeline", "extract_relations"):
            candidates = self.agent_scheduler.extract(graph)

        with log_step("pipeline", "verify"):
            graph = self.verifier.verify(candidates, graph)

        # 2. Human-in-the-loop review checkpoint
        if self.settings.human_loop.enabled:
            with log_step("pipeline", "human_review"):
                if corrections is not None:
                    review = self.human_reviewer.review_with_corrections(
                        graph, request.problem_text, corrections,
                        out_dir=self.settings.human_loop.out_dir,
                    )
                elif self.settings.human_loop.interactive:
                    review = self.human_reviewer.review_interactive(
                        graph, request.problem_text,
                        out_dir=self.settings.human_loop.out_dir,
                    )
                else:
                    review = self.human_reviewer.review(
                        graph, request.problem_text,
                        out_dir=self.settings.human_loop.out_dir,
                    )
                if review.corrected_graph is not None:
                    graph = review.corrected_graph

        # 3. DSL
        with log_step("pipeline", "to_dsl"):
            dsl_text = self.dsl_serializer(graph, self.settings.dsl)

        # 4. Enhanced reasoning (with knowledge + code tools, scoped to grade)
        with log_step("pipeline", "reason", grade=request.grade.value):
            agent = self._agent_for_grade(request.grade)
            plan = agent.reason(dsl_text, request.problem_text, self._tools(graph))

        # 5. Symbolic solving
        with log_step("pipeline", "solve"):
            solution = self.solver.solve(plan, graph)

        # 6. Auto-generate LaTeX solution report PDF
        pdf_path = None
        try:
            with log_step("pipeline", "report"):
                from .human_loop.pdf_compiler import solution_to_pdf
                out_dir = Path(self.settings.human_loop.out_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = solution_to_pdf(
                    request.problem_text, solution, graph,
                    out_path=str(out_dir / "solution_report.pdf"),
                )
        except Exception as e:
            log_step("pipeline", "report", error=str(e)).__enter__() and None

        resp = SolveResponse(
            answer=solution.answer,
            confidence=solution.confidence,
            proof=solution.proof,
            verified=solution.verified,
            verification_log=solution.verification_log,
        )
        resp._pdf_path = pdf_path
        return resp


def solve(
    request: SolveRequest,
    settings: Settings | None = None,
    corrections: list[Correction] | None = None,
) -> SolveResponse:
    return GeometryPipeline(settings).run(request, corrections=corrections)
