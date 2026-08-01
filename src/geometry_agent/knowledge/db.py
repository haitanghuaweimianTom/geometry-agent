"""Knowledge database: holds curated + persistent entries/methods, and provides
keyword+tag based retrieval with subject filtering and on-demand web fallback.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import KnowledgeConfig
from ..logging_util import info
from ..types import KnowledgeEntry, MethodEntry, MethodPriority, RetrievedKnowledge, SubjectType
from .curated import CURATED_ENTRIES, CURATED_METHODS
from .subject_classifier import classify_subject
from .web_retriever import WebRetriever

_PUNCT = "，。、；：？！,.;:?!()（）[]【】\"' \t\n\r/\\|"


def _tokenize(query: str) -> list[str]:
    if not query:
        return []
    for ch in _PUNCT:
        query = query.replace(ch, " ")
    return [t for t in query.split() if t]


class KnowledgeDB:
    """Curated + persistent knowledge store with simple retrieval."""

    def __init__(
        self,
        config: Optional[KnowledgeConfig] = None,
        web_retriever: Optional[WebRetriever] = None,
    ):
        self.config = config or KnowledgeConfig()
        self._entries: list[KnowledgeEntry] = list(CURATED_ENTRIES)
        self._methods: list[MethodEntry] = list(CURATED_METHODS)
        self._seen_ids: set[str] = {e.id for e in self._entries}
        self.web_retriever = web_retriever
        self._load_persistent()

    # ------------------------------------------------------------------ loading
    def _load_persistent(self) -> None:
        path = Path(self.config.db_path)
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            info("knowledge.db", "load_failed", path=str(path), error=repr(e))
            return
        items = data.get("entries", []) if isinstance(data, dict) else []
        for it in items:
            if not isinstance(it, dict):
                continue
            try:
                entry = KnowledgeEntry(**it)
            except Exception:
                continue
            if entry.id not in self._seen_ids:
                self._entries.append(entry)
                self._seen_ids.add(entry.id)

    def _persist(self) -> None:
        path = Path(self.config.db_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            web_entries = [e.model_dump() for e in self._entries if e.source == "web"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"entries": web_entries}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            info("knowledge.db", "persist_failed", path=str(path), error=repr(e))

    # ------------------------------------------------------------------- search
    def search(
        self,
        query: str,
        subject: Optional[SubjectType] = None,
        k: int = 8,
    ) -> list[KnowledgeEntry]:
        terms = _tokenize(query)
        scored: list[tuple[float, KnowledgeEntry]] = []
        for e in self._entries:
            if subject is not None and e.subject != subject:
                continue
            score = self._score_entry(e, query, terms)
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def search_methods(
        self,
        subject: SubjectType,
        k: int = 5,
    ) -> list[MethodEntry]:
        methods = [m for m in self._methods if m.subject == subject]
        methods.sort(key=lambda m: (m.priority.value, m.id))
        return methods[:k]

    # ------------------------------------------------------------------ scoring
    @staticmethod
    def _score_entry(
        entry: KnowledgeEntry, query: str, terms: list[str]
    ) -> float:
        tags_str = " ".join(entry.tags)
        applies_str = " ".join(entry.applies_to)
        hay = f"{entry.title} {entry.content} {tags_str} {applies_str}"
        score = 0.0
        for term in terms:
            if not term:
                continue
            if term in entry.title:
                score += 3.0
            elif term in hay:
                score += 1.0
            if term in tags_str:
                score += 2.0
            if term in applies_str:
                score += 2.0
        keywords = set(entry.tags) | set(entry.applies_to)
        for kw in keywords:
            if kw and len(kw) >= 1 and kw in query:
                weight = 3.0 if len(kw) >= 2 else 1.5
                score += weight
        return score

    # --------------------------------------------------------------- mutations
    def add_entry(self, entry: KnowledgeEntry) -> None:
        if entry.id in self._seen_ids:
            return
        self._entries.append(entry)
        self._seen_ids.add(entry.id)
        if entry.source == "web":
            self._persist()

    # --------------------------------------------------------------- retrieve
    def retrieve(
        self,
        query: str,
        subject: Optional[SubjectType] = None,
    ) -> RetrievedKnowledge:
        subj = subject or classify_subject(query)
        entries = self.search(query, subject=subj, k=8)
        methods = self.search_methods(subj, k=5)
        from_web = False

        if (
            len(entries) < self.config.min_local_entries
            and self.config.web_enabled
            and self.web_retriever is not None
        ):
            try:
                web_entries = self.web_retriever.fetch(query, subject=subj)
            except Exception as e:
                info("knowledge.db", "web_error", query=query, error=repr(e))
                web_entries = []
            for we in web_entries:
                self.add_entry(we)
            if web_entries:
                entries = entries + web_entries
                from_web = True

        return RetrievedKnowledge(
            topic=subj,
            entries=entries,
            methods=methods,
            from_web=from_web,
        )

    # --------------------------------------------------------------- utilities
    def all_entries(self) -> list[KnowledgeEntry]:
        return list(self._entries)

    def all_methods(self) -> list[MethodEntry]:
        return list(self._methods)

    def entries_by_subject(self, subject: SubjectType) -> list[KnowledgeEntry]:
        return [e for e in self._entries if e.subject == subject]


__all__ = [
    "KnowledgeDB",
    "MethodPriority",
]
