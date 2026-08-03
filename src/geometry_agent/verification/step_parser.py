"""Natural-language step -> formal claim parser (Chinese+formula to SymPy)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import sympy as sp


rel_map = {"=": sp.Eq, ">=": sp.Ge, "<=": sp.Le, ">": sp.Gt, "<": sp.Lt}

_REL_PATTERN = re.compile(r"(>=|<=|>|<|=)")

_POWER_SUPS = {
    "²": "**2",
    "³": "**3",
}

_CHINESE_PAREN_OPEN = "（"
_CHINESE_PAREN_CLOSE = "）"
_CHINESE_COMMA = "，"
_CDOT = "·"
_TIMES = "×"
_DIV = "÷"

# Match implicit multiplication: digit-followed-by-letter/func, letter-followed-by-open-paren,
# letter-followed-by-letter (multi-char identifier greediness handled by sympify so we do simple
# letter-letter for single-letter-variable convention typical of geometry problems).
_IMPLICIT_MUL_PATTERNS = [
    (re.compile(r"(\d)\s*\("), r"\1*("),  # 2(
    (re.compile(r"(\d)\s*([a-zA-Z])"), r"\1*\2"),  # 2a
    (re.compile(r"([a-zA-Z])\s*\("), r"\1*("),  # a(
    (re.compile(r"(\))\s*([a-zA-Z0-9])"), r")*\2"),  # )a or )2
    (re.compile(r"(\))\s*\("), r")*("),  # )(
]


def _normalize(text: str) -> str:
    s = text.strip()
    s = s.replace(_CHINESE_PAREN_OPEN, "(").replace(_CHINESE_PAREN_CLOSE, ")")
    s = s.replace(_CHINESE_COMMA, ",")
    s = s.replace(_CDOT, "*").replace(_TIMES, "*")
    s = s.replace(_DIV, "/")
    for k, v in _POWER_SUPS.items():
        s = s.replace(k, v)
    s = s.replace("^", "**")
    # Protect function names by replacing them with placeholders so letter-letter
    # splitting doesn't break them.
    _FUNCS = ("sqrt", "sin", "cos", "tan", "exp", "log", "abs", "asin", "acos", "atan")
    placeholders = {}
    for i, f in enumerate(_FUNCS):
        ph = f"\x00F{i}\x00"
        placeholders[ph] = f
        s = re.sub(rf"\b{f}\b", ph, s)
    for pat, repl in _IMPLICIT_MUL_PATTERNS:
        s = pat.sub(repl, s)
    # Iteratively split adjacent letter pairs into products where appropriate.
    # Single-letter lowercase variables are the algebra convention (a,b,x,y,n,...);
    # we keep uppercase-uppercase pairs together (geometry segment labels like AB, CD).
    def _split_letter_pairs(m):
        a, b = m.group(1), m.group(2)
        if a.isupper() and b.isupper():
            return a + b
        return a + "*" + b

    for _ in range(10):
        new_s = re.sub(r"([a-zA-Z])([a-zA-Z])", _split_letter_pairs, s)
        if new_s == s:
            break
        s = new_s
    for ph, f in placeholders.items():
        s = s.replace(ph, f)
    return s


def _split_relation(text: str) -> Optional[Tuple[str, str, str]]:
    norm = _normalize(text)
    matches = list(_REL_PATTERN.finditer(norm))
    if not matches:
        return None
    m = matches[0]
    lhs = norm[: m.start()].strip()
    rel = m.group(1)
    rhs = norm[m.end() :].strip()
    if not lhs or not rhs:
        return None
    return lhs, rel, rhs


def _sympify_safe(s: str):
    try:
        return sp.sympify(s)
    except Exception:
        return None


def parse_claim(statement: str):
    parts = _split_relation(statement)
    if parts is None:
        return None
    lhs_s, rel_s, rhs_s = parts
    if rel_s not in rel_map:
        return None
    lhs = _sympify_safe(lhs_s)
    rhs = _sympify_safe(rhs_s)
    if lhs is None or rhs is None:
        return None
    return (lhs, rel_map[rel_s], rhs)


def parse_expr(text: str):
    try:
        return sp.sympify(_normalize(text))
    except Exception:
        return None
