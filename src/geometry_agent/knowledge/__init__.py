"""Knowledge base package: local curated KB + on-demand web retrieval.

Public API:
  - KnowledgeManager: high-level facade for retrieving and formatting knowledge.
  - KnowledgeDB: low-level store with search/retrieve.
  - WebRetriever / fetch_web_knowledge: on-demand web retrieval with fallback.
  - classify_subject: rule-based subject classifier.
  - CURATED_ENTRIES / CURATED_METHODS: the local curated content.
"""
from __future__ import annotations

from .curated import CURATED_ENTRIES, CURATED_METHODS
from .db import KnowledgeDB
from .manager import KnowledgeManager
from .subject_classifier import classify_subject
from .web_retriever import WebRetriever, fetch_web_knowledge

__all__ = [
    "CURATED_ENTRIES",
    "CURATED_METHODS",
    "KnowledgeDB",
    "KnowledgeManager",
    "WebRetriever",
    "classify_subject",
    "fetch_web_knowledge",
]
