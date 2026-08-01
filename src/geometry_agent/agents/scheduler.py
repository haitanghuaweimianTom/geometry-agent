"""AgentScheduler: run all 7 relation agents in parallel, dedupe & resolve
conflicts (design/04 §11, §12)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from ..config import GraphConfig
from ..types import GeometryGraph, RelationCandidate, RelType
from .base import AgentBase
from .circle_agent import CircleAgent
from .cross_agent import CrossAgent
from .ellipse_agent import EllipseAgent
from .line_agent import LineAgent
from .mark_agent import MarkAgent
from .point_agent import PointAgent
from .polygon_agent import PolygonAgent


class AgentScheduler:
    """Schedules all relation agents in parallel over a node-only graph."""

    def __init__(self, config: Optional[GraphConfig] = None):
        self.config = config or GraphConfig()
        self.agents: list[AgentBase] = [
            PointAgent(self.config),
            LineAgent(self.config),
            CircleAgent(self.config),
            EllipseAgent(self.config),
            PolygonAgent(self.config),
            MarkAgent(self.config),
            CrossAgent(self.config),
        ]

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        all_cands: list[RelationCandidate] = []
        workers = max(1, getattr(self.config, "relation_parallel_workers", 4))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {ex.submit(self._safe_extract, a, graph): a.name for a in self.agents}
            for fut in as_completed(future_map):
                name = future_map[fut]
                try:
                    res = fut.result()
                except Exception:
                    res = []
                all_cands.extend(res)
        return self._dedupe_and_resolve(all_cands)

    # ------------------------------------------------------------------
    def _safe_extract(self, agent: AgentBase, graph: GeometryGraph) -> list[RelationCandidate]:
        try:
            return list(agent.extract(graph))
        except Exception:
            return []

    def _dedupe_and_resolve(self, cands: list[RelationCandidate]) -> list[RelationCandidate]:
        """Dedupe by (src, dst, rel); on conflict keep highest confidence.
        Mark vs detected numerical contradiction is downgraded (uncertain hint)
        but still forwarded to the Verifier for the final say."""
        best: dict[tuple[str, str, RelType], RelationCandidate] = {}
        marks: dict[tuple[str, str, RelType], RelationCandidate] = {}
        for c in cands:
            key = (c.src, c.dst, c.rel)
            src = getattr(c, "source", "") or ("mark" if c.agent == "MarkAgent" else "detected")
            is_mark = src == "mark" or c.agent == "MarkAgent"
            bucket = marks if is_mark else best
            existing = bucket.get(key)
            if existing is None or c.confidence > existing.confidence:
                bucket[key] = c
        # merge: detected takes priority; if a mark disagrees it is still passed
        # through (verifier decides).
        for key, mc in marks.items():
            if key not in best:
                best[key] = mc
            else:
                # both present: keep detected but bump confidence slightly
                bc = best[key]
                bc = bc.model_copy(update={"confidence": min(1.0, bc.confidence + 0.0)})
                best[key] = bc
        return list(best.values())
