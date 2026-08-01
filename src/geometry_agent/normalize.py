"""Input text normalization for user-typed problem statements.

Chinese IME input often produces full-width digits, letters and punctuation
（Ａ（１，２）ｘ²＋ｙ²＝１）, which breaks SymPy parsing, coordinate regexes
and the LLM's tool calls. Every entry point (CLI, Web UI, API) routes the
problem text through :func:`normalize_problem_text` before solving.

Chinese sentence punctuation （。？！、）is deliberately left untouched so the
PDF report keeps proper CJK typography.
"""

from __future__ import annotations

_KEEP_FULLWIDTH = {"\uFF01", "\uFF1F"}  # ！？ stay full-width for CJK typography


def _build_table() -> dict[int, str]:
    table = {ord("　"): " ", ord("−"): "-"}  # full-width space, U+2212 minus
    for cp in range(0xFF01, 0xFF5F):
        ch = chr(cp)
        if ch not in _KEEP_FULLWIDTH:
            table[cp] = chr(cp - 0xFEE0)
    return table


_TABLE = _build_table()


def normalize_problem_text(text: str) -> str:
    """Convert full-width digits/letters/punctuation to half-width.

    Idempotent and safe on empty input. Chinese sentence punctuation
    （。？！、）and math symbols (× ÷ ² ³ ⁻ ⌒ ∠ …) are left untouched —
    the report layer converts those at render time.
    """
    if not text:
        return text
    return text.translate(_TABLE)
