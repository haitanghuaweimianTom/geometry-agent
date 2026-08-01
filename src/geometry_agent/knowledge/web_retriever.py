"""On-demand web knowledge retriever.

Tries to fetch supplementary knowledge from a public search endpoint (DuckDuckGo
Lite HTML) via httpx and parse result snippets into KnowledgeEntry objects.

Design goal: provide the interface and graceful degradation. Retrieval quality
is NOT the priority - any network/parse failure must return an empty list and
log a warning, never raise.
"""
from __future__ import annotations

import re
from typing import Optional

from ..config import KnowledgeConfig
from ..logging_util import info
from ..types import KnowledgeEntry, SubjectType
from .subject_classifier import classify_subject

_DD_URL = "https://lite.duckduckgo.com/lite/"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _warn(msg: str, **extra: object) -> None:
    info("knowledge.web", "warn", msg=msg, **extra)


class WebRetriever:
    """Retrieve supplementary knowledge entries from the web, with graceful fallback."""

    def __init__(self, config: Optional[KnowledgeConfig] = None):
        self.config = config or KnowledgeConfig()
        self.timeout = self.config.web_timeout

    def fetch(
        self,
        query: str,
        subject: Optional[SubjectType] = None,
        max_results: int = 5,
    ) -> list[KnowledgeEntry]:
        if not self.config.web_enabled or not query:
            return []
        try:
            import httpx  # type: ignore
        except Exception as e:  # pragma: no cover - httpx is a declared dep
            _warn("httpx_unavailable", error=repr(e))
            return []

        subj = subject or classify_subject(query)
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = client.get(_DD_URL, params={"q": query, "kl": "cn-zh"})
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            _warn("fetch_failed", query=query, error=repr(e))
            return []

        try:
            entries = self._parse_ddg(html, query, subj)
        except Exception as e:
            _warn("parse_failed", query=query, error=repr(e))
            return []

        return entries[:max_results]

    @staticmethod
    def _parse_ddg(
        html: str, query: str, subject: SubjectType
    ) -> list[KnowledgeEntry]:
        titles = re.findall(r'class="result-link"[^>]*>([^<]+)</a>', html)
        snippets = re.findall(
            r'class="result-snippet"[^>]*>(.*?)</td>', html, re.S
        )
        out: list[KnowledgeEntry] = []
        base = abs(hash(query)) % 10**8
        for i, (title, snippet) in enumerate(zip(titles, snippets)):
            text = re.sub(r"<[^>]+>", "", snippet).strip()
            if not text:
                continue
            out.append(
                KnowledgeEntry(
                    id=f"web-{base}-{i}",
                    subject=subject,
                    title=title.strip()[:120] or f"web:{query}",
                    content=text[:500],
                    tags=[query, "web"],
                    applies_to=[query],
                    source="web",
                )
            )
        return out


def fetch_web_knowledge(
    query: str,
    subject: Optional[SubjectType] = None,
    config: Optional[KnowledgeConfig] = None,
) -> list[KnowledgeEntry]:
    """Convenience function: create a WebRetriever and fetch in one call."""
    return WebRetriever(config).fetch(query, subject)
