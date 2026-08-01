"""VerifierEngine: dispatch candidates to per-rel verifiers, write verified
edges & evidence back into the GeometryGraph (design/05 §2.2, §5)."""

from __future__ import annotations

from typing import Any, Optional

from ..config import VerifierConfig
from ..types import (
    Edge,
    GeometryGraph,
    Node,
    RelType,
    RelationCandidate,
    VerifyResult,
    VerifyState,
)
from .verifiers.angle_verifier import ParallelVerifier, PerpendicularVerifier
from .verifiers.equality_verifier import EqualityVerifier
from .verifiers.on_verifier import OnVerifier
from .verifiers.relation_verifier import (
    CollinearVerifier,
    ConcentricVerifier,
    InscribedVerifier,
    IntersectVerifier,
)
from .verifiers.tangent_verifier import TangentVerifier


class VerifierEngine:
    """Three-state constraint verifier with adaptive tolerance."""

    def __init__(self, config: Optional[VerifierConfig] = None):
        self.config = config or VerifierConfig()
        self._graph: Optional[GeometryGraph] = None
        self._node_lookup: dict[str, Node] = {}
        self.verification_log: list[dict[str, Any]] = []
        self._verifiers = {
            RelType.ON.value: OnVerifier(self.config),
            RelType.PERPENDICULAR.value: PerpendicularVerifier(self.config),
            RelType.PARALLEL.value: ParallelVerifier(self.config),
            RelType.TANGENT.value: TangentVerifier(self.config),
            RelType.EQUAL.value: EqualityVerifier(self.config),
            RelType.COLLINEAR.value: CollinearVerifier(self.config),
            RelType.CONCENTRIC.value: ConcentricVerifier(self.config),
            RelType.INTERSECT.value: IntersectVerifier(self.config),
            RelType.INSCRIBED.value: InscribedVerifier(self.config),
        }

    # ------------------------------------------------------------------
    def attach(self, graph: GeometryGraph) -> None:
        """Bind a graph so verify_one can resolve node ids."""
        self._graph = graph
        self._node_lookup = {n.id: n for n in graph.nodes}

    def verify(self, candidates: list[RelationCandidate], graph: GeometryGraph) -> GeometryGraph:
        """Verify every candidate and append an Edge (true/uncertain) to the graph.
        False candidates are dropped per design/03 §6.3."""
        self.attach(graph)
        for cand in candidates:
            res = self.verify_one(cand.rel, cand.src, cand.dst, dict(cand.attrs))
            if res.verified == VerifyState.FALSE:
                continue
            confidence = cand.confidence
            if res.verified == VerifyState.UNCERTAIN:
                confidence = cand.confidence * 0.5
            merged_attrs: dict[str, Any] = dict(cand.attrs)
            for k, v in res.attrs.items():
                merged_attrs.setdefault(k, v)
            edge = Edge(
                src=cand.src,
                dst=cand.dst,
                rel=cand.rel,
                confidence=confidence,
                verified=res.verified,
                evidence=res.evidence,
                source=getattr(cand, "source", "detected") or "detected",
                attrs=merged_attrs,
            )
            graph.edges.append(edge)
        return graph

    # ------------------------------------------------------------------
    def verify_one(self, rel: Any, src: Any, dst: Any, attrs: dict) -> VerifyResult:
        """Verify a single relation. `src`/`dst` may be node ids or Node objs."""
        rel_name = rel.value if isinstance(rel, RelType) else str(rel)
        src_node = src if isinstance(src, Node) else self._node_lookup.get(str(src))
        dst_node = dst if isinstance(dst, Node) else self._node_lookup.get(str(dst))
        attrs = attrs or {}
        if src_node is None or dst_node is None:
            res = VerifyResult(
                verified=VerifyState.FALSE,
                evidence=f"node not found: src={src}, dst={dst}",
            )
        else:
            v = self._verifiers.get(rel_name)
            if v is None:
                res = VerifyResult(
                    verified=VerifyState.FALSE,
                    evidence=f"no verifier for rel '{rel_name}'",
                )
            else:
                try:
                    res = v.verify(src_node, dst_node, attrs)
                except Exception as ex:
                    res = VerifyResult(
                        verified=VerifyState.FALSE,
                        evidence=f"{rel_name} verifier raised: {ex}",
                    )
        self.verification_log.append(
            {
                "step": "relation",
                "rel": rel_name,
                "src": src_node.id if src_node is not None else str(src),
                "dst": dst_node.id if dst_node is not None else str(dst),
                "measured": dict(res.measured),
                "verified": res.verified.value,
                "evidence": res.evidence,
                "attrs": dict(res.attrs),
            }
        )
        return res
