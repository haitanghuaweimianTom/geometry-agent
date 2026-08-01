"""Unit tests for the knowledge base module (local curated + web retrieval)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from geometry_agent.config import KnowledgeConfig
from geometry_agent.knowledge.curated import (
    CURATED_ENTRIES,
    CURATED_METHODS,
    entries_by_subject,
    methods_by_subject,
)
from geometry_agent.knowledge.db import KnowledgeDB
from geometry_agent.knowledge.manager import KnowledgeManager
from geometry_agent.knowledge.subject_classifier import classify_subject
from geometry_agent.knowledge.web_retriever import WebRetriever
from geometry_agent.types import MethodPriority, SubjectType


# --------------------------------------------------------------------------- #
# 1. classify_subject: 4 disciplines
# --------------------------------------------------------------------------- #
def test_classify_subject_plane_default():
    assert classify_subject("AB 切圆 O 于 A, 求证 OA⊥AB") == SubjectType.PLANE_GEOMETRY


def test_classify_subject_triangle():
    assert classify_subject("在 △ABC 中已知 b=8, c=6, ∠A=60°, 用余弦定理求 a") == (
        SubjectType.TRIANGLE_SOLVING
    )


def test_classify_subject_analytic():
    assert classify_subject("求椭圆 x²/25 + y²/9 = 1 的焦点坐标与离心率") == (
        SubjectType.ANALYTIC_GEOMETRY
    )


def test_classify_subject_solid():
    assert classify_subject("正三棱锥的侧面与底面所成二面角为 60°, 求体积") == (
        SubjectType.SOLID_GEOMETRY
    )


# --------------------------------------------------------------------------- #
# 2. KnowledgeDB.search("切线") returns non-empty tangent-related entries
# --------------------------------------------------------------------------- #
def test_db_search_tangent_nonempty():
    db = KnowledgeDB(KnowledgeConfig(web_enabled=False))
    results = db.search("切线")
    assert len(results) > 0
    assert any("切线" in e.title or "切线" in " ".join(e.tags) for e in results)


# --------------------------------------------------------------------------- #
# 3. search_methods(plane_geometry) sorted by priority ascending, IN_CLASS first
# --------------------------------------------------------------------------- #
def test_search_methods_sorted_by_priority():
    db = KnowledgeDB(KnowledgeConfig(web_enabled=False))
    methods = db.search_methods(SubjectType.PLANE_GEOMETRY, k=10)
    assert len(methods) >= 4
    priorities = [m.priority.value for m in methods]
    assert priorities == sorted(priorities), "methods must be sorted by priority asc"
    assert methods[0].priority == MethodPriority.IN_CLASS
    assert all(
        methods[i].priority.value <= methods[i + 1].priority.value
        for i in range(len(methods) - 1)
    )


# --------------------------------------------------------------------------- #
# 4. retrieve with enough local entries does NOT touch the web
# --------------------------------------------------------------------------- #
def test_retrieve_no_web_when_local_sufficient():
    cfg = KnowledgeConfig(web_enabled=True, min_local_entries=3)
    retriever = WebRetriever(cfg)
    db = KnowledgeDB(cfg, web_retriever=retriever)
    fetched_calls: list[str] = []

    def fake_fetch(query, subject=None, max_results=5):
        fetched_calls.append(query)
        return []

    with patch.object(retriever, "fetch", side_effect=fake_fetch):
        rk = db.retrieve("切线 圆 垂直", subject=SubjectType.PLANE_GEOMETRY)
    assert rk.from_web is False
    assert fetched_calls == [], "web must not be called when local entries are sufficient"
    assert len(rk.entries) >= 3
    assert len(rk.methods) > 0
    assert rk.topic == SubjectType.PLANE_GEOMETRY


# --------------------------------------------------------------------------- #
# 5. format_for_prompt contains "推荐" and a method name
# --------------------------------------------------------------------------- #
def test_format_for_prompt_contains_recommendation_and_methods():
    mgr = KnowledgeManager(KnowledgeConfig(web_enabled=False))
    rk = mgr.get_knowledge("AB 切圆 O 于 A, 求证 OA⊥AB")
    text = mgr.format_for_prompt(rk)
    assert "推荐" in text
    assert any(m.name in text for m in rk.methods), "method names should appear"
    assert "课内方法" in text


# --------------------------------------------------------------------------- #
# 6. WebRetriever.fetch returns [] on network failure without raising
# --------------------------------------------------------------------------- #
def test_web_retriever_fetch_returns_empty_on_failure():
    import httpx

    retriever = WebRetriever(KnowledgeConfig(web_enabled=True, web_timeout=1.0))

    def boom(*a, **kw):
        raise RuntimeError("simulated network down")

    with patch.object(httpx, "Client", side_effect=boom):
        result = retriever.fetch("切线性质")
    assert result == []


def test_web_retriever_disabled_returns_empty():
    retriever = WebRetriever(KnowledgeConfig(web_enabled=False))
    assert retriever.fetch("anything") == []


# --------------------------------------------------------------------------- #
# 7. Curated base covers 4 subjects, each with >=5 entries
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "subject",
    list(SubjectType),
)
def test_curated_coverage_per_subject(subject):
    es = entries_by_subject(subject)
    ms = methods_by_subject(subject)
    assert len(es) >= 5, f"{subject}: only {len(es)} entries"
    assert len(ms) >= 4, f"{subject}: only {len(ms)} methods"


def test_curated_total_reasonable():
    assert len(CURATED_ENTRIES) >= 8 * 4
    assert len(CURATED_METHODS) >= 4 * 4
    subjects = {e.subject for e in CURATED_ENTRIES}
    assert subjects == set(SubjectType)


# --------------------------------------------------------------------------- #
# Bonus: manager + classifier integration smoke test
# --------------------------------------------------------------------------- #
def test_manager_get_knowledge_analytic():
    mgr = KnowledgeManager(KnowledgeConfig(web_enabled=False))
    rk = mgr.get_knowledge("求椭圆 x²/25+y²/9=1 的焦点弦长")
    assert rk.topic == SubjectType.ANALYTIC_GEOMETRY
    assert len(rk.methods) > 0
    assert all(m.subject == SubjectType.ANALYTIC_GEOMETRY for m in rk.methods)
