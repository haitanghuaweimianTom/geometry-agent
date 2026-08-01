"""Geometry Theorem Database (design/08 §3)."""

from __future__ import annotations

from pathlib import Path

from ..types import Theorem

_DEFAULT_PATH = Path(__file__).resolve().parent / "theorems.json"


class TheoremDB:
    """Loads theorems from JSON and provides keyword-based retrieval (RAG placeholder)."""

    def __init__(self, path: str | Path | None = None):
        path = Path(path) if path else _DEFAULT_PATH
        if not path.exists():
            path = _DEFAULT_PATH
        self.path = path
        self._theorems: list[Theorem] = []
        self._load()

    def _load(self) -> None:
        import json

        if not self.path.exists():
            self._theorems = []
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._theorems = []
            return
        items = data.get("theorems", data) if isinstance(data, dict) else data
        out: list[Theorem] = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                try:
                    out.append(Theorem(**it))
                except Exception:
                    continue
        self._theorems = out

    def all_theorems(self) -> list[Theorem]:
        return list(self._theorems)

    def search(self, query: str, k: int = 5) -> list[Theorem]:
        if not query or not self._theorems:
            return list(self._theorems[:k])
        terms = [t for t in query.replace("，", " ").replace(",", " ").split() if t]
        scored: list[tuple[float, Theorem]] = []
        for th in self._theorems:
            hay = " ".join(
                [
                    th.name,
                    th.conclusion,
                    th.condition,
                    th.category,
                    " ".join(th.premise),
                ]
            )
            score = 0.0
            for term in terms:
                if term in hay:
                    score += 1.0
                if term in th.name:
                    score += 1.5
                if term in th.category:
                    score += 1.0
            if score > 0:
                scored.append((score, th))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:k]]
