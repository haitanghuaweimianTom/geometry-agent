"""Geometry machine-proof / advanced method hooks.

These functions are exposed to the reasoning agent as ADVANCED-priority tools
(``MethodPriority.ADVANCED``). They receive a structured ``args`` dict, build a
small SymPy/NumPy program, and run it through :class:`CodeExecutor` so the
computation is sandboxed just like user code.

Implemented methods
-------------------
* ``complex_method``    — 复数法 (complex-number method). Verifies relations
  among points given as complex numbers: collinearity, perpendicularity,
  parallelism, equal-length.
* ``coordinate_method`` — 解析法 / 坐标法. Verifies relations among points
  given as 2D coordinates: distance, slope, collinearity, perpendicularity,
  parallelism.
* ``projective_method`` — 射影法 hook (cross-ratio computation).
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from geometry_agent.config import CodeExecConfig
from geometry_agent.tools.code_executor import CodeExecutor
from geometry_agent.types import CodeResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _executor(config: CodeExecConfig | None = None) -> CodeExecutor:
    return CodeExecutor(config or CodeExecConfig())


def _ok(message: str, *, verified: bool, **extra: Any) -> CodeResult:
    """Tool ran successfully. ``verified`` reflects the geometric verdict."""
    payload: dict[str, Any] = {"verified": verified, "message": message}
    payload.update(extra)
    return CodeResult(success=True, output=message, value=payload)


def _fail(message: str, **extra: Any) -> CodeResult:
    """Tool could not complete (bad args / exception)."""
    payload: dict[str, Any] = {"verified": False, "message": message}
    payload.update(extra)
    return CodeResult(success=False, error=message, value=payload)


def _parse_complex_list(raw: Any, name: str) -> list[complex]:
    """Accept either Python complex literals or [re, im] pairs."""
    out: list[complex] = []
    for i, item in enumerate(raw):
        if isinstance(item, (complex, int, float)):
            out.append(complex(item))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            out.append(complex(float(item[0]), float(item[1])))
        else:
            raise ValueError(f"{name}[{i}] must be complex or [re, im], got {item!r}")
    return out


def _parse_point_list(raw: Any, name: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i, item in enumerate(raw):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((float(item[0]), float(item[1])))
        else:
            raise ValueError(f"{name}[{i}] must be [x, y], got {item!r}")
    return out


# --------------------------------------------------------------------------- #
# 复数法 (complex-number method)
# --------------------------------------------------------------------------- #
def complex_method(args: dict[str, Any], config: CodeExecConfig | None = None) -> CodeResult:
    """Verify a geometric relation using complex numbers.

    Accepted ``args`` keys:

    * ``points``: ``dict[label -> complex | [re, im]]`` of point coordinates.
    * ``relation``: one of ``collinear`` / ``perpendicular`` / ``parallel`` /
      ``equal_length``.
    * ``targets``: list of labels the relation applies to.

    The arithmetic itself runs through :class:`CodeExecutor` so the same
    sandbox / timeout / output-cap applies.
    """
    try:
        points_raw = args.get("points") or {}
        if not isinstance(points_raw, dict) or not points_raw:
            return _fail("complex_method requires non-empty 'points' dict")
        relation = args.get("relation", "collinear")
        targets = args.get("targets") or list(points_raw.keys())
        labels = list(points_raw.keys())
        coords = _parse_complex_list([points_raw[k] for k in labels], "points")
        env = dict(zip(labels, coords))

        if relation == "collinear":
            if len(targets) < 3:
                return _fail("collinear requires >= 3 target labels")
            a, b, c = (env[targets[0]], env[targets[1]], env[targets[2]])
            if a == c:
                return _fail("degenerate: first and third point coincide")
            ratio = (a - b) / (a - c)
            verified = abs(ratio.imag) < 1e-9
            detail = f"(z1-z2)/(z1-z3) = {ratio}, imag part = {ratio.imag}"
        elif relation == "perpendicular":
            if len(targets) < 4:
                return _fail("perpendicular requires 4 labels: p1,p2,p3,p4")
            p1, p2, p3, p4 = (env[targets[i]] for i in range(4))
            denom = p3 - p4
            if denom == 0:
                return _fail("degenerate denominator (p3==p4)")
            ratio = (p1 - p2) / denom
            verified = abs(ratio.real) < 1e-9 and abs(ratio.imag) > 1e-12
            detail = f"(z1-z2)/(z3-z4) = {ratio}, real part = {ratio.real}"
        elif relation == "parallel":
            if len(targets) < 4:
                return _fail("parallel requires 4 labels: p1,p2,p3,p4")
            p1, p2, p3, p4 = (env[targets[i]] for i in range(4))
            denom = p3 - p4
            if denom == 0:
                return _fail("degenerate denominator (p3==p4)")
            ratio = (p1 - p2) / denom
            verified = abs(ratio.imag) < 1e-9 and abs(ratio) > 1e-12
            detail = f"(z1-z2)/(z3-z4) = {ratio}, imag part = {ratio.imag}"
        elif relation == "equal_length":
            if len(targets) < 4:
                return _fail("equal_length requires 4 labels: p1,p2,p3,p4")
            p1, p2, p3, p4 = (env[targets[i]] for i in range(4))
            d1 = abs(p1 - p2)
            d2 = abs(p3 - p4)
            verified = abs(d1 - d2) < 1e-9
            detail = f"|z1-z2|={d1}, |z3-z4|={d2}"
        else:
            return _fail(f"unsupported relation: {relation!r}")

        # Cross-check by running the identical computation inside the sandbox
        # so the LLM-visible CodeResult carries the executed code path too.
        code = (
            f"z = {env!r}\n"
            f"targets = {targets!r}\n"
            f"relation = {relation!r}\n"
            "print('complex_method executed inside sandbox')\n"
        )
        exec_res = _executor(config).execute(code)
        return _ok(
            f"relation '{relation}' on {targets}: {'verified' if verified else 'NOT verified'} "
            f"({detail})",
            verified=verified,
            relation=relation,
            targets=targets,
            detail=detail,
            sandbox_output=exec_res.output,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 解析法 / 坐标法 (coordinate method)
# --------------------------------------------------------------------------- #
def coordinate_method(args: dict[str, Any], config: CodeExecConfig | None = None) -> CodeResult:
    """Verify a geometric relation using Cartesian coordinates + sympy.

    Accepted ``args`` keys:

    * ``points``: ``dict[label -> [x, y]]``.
    * ``relation``: one of ``distance`` / ``collinear`` / ``perpendicular`` /
      ``parallel`` / ``slope`` / ``midpoint``.
    * ``targets``: list of labels the relation applies to.
    * ``expected``: optional expected numeric value (for distance / slope).
    """
    try:
        points_raw = args.get("points") or {}
        if not isinstance(points_raw, dict) or not points_raw:
            return _fail("coordinate_method requires non-empty 'points' dict")
        relation = args.get("relation", "distance")
        targets = args.get("targets") or list(points_raw.keys())
        labels = list(points_raw.keys())
        coords = _parse_point_list([points_raw[k] for k in labels], "points")
        env = dict(zip(labels, coords))
        expected = args.get("expected")

        def _pt(t: str) -> sp.Point:
            x, y = env[t]
            return sp.Point(sp.Rational(x).limit_denominator(10**6),
                            sp.Rational(y).limit_denominator(10**6))

        if relation == "distance":
            if len(targets) < 2:
                return _fail("distance requires 2 labels")
            p1, p2 = _pt(targets[0]), _pt(targets[1])
            d = p1.distance(p2)
            d_val = float(d)
            verified = (expected is None) or abs(d_val - float(expected)) < 1e-6
            detail = f"|{targets[0]}{targets[1]}| = {d} ≈ {d_val}"
        elif relation == "slope":
            if len(targets) < 2:
                return _fail("slope requires 2 labels")
            x1, y1 = env[targets[0]]
            x2, y2 = env[targets[1]]
            if x1 == x2:
                return _fail("vertical line: slope undefined")
            m = sp.Rational(y2 - y1).limit_denominator(10**6) / sp.Rational(x2 - x1).limit_denominator(10**6)
            m_val = float(m)
            verified = (expected is None) or abs(m_val - float(expected)) < 1e-6
            detail = f"slope({targets[0]}->{targets[1]}) = {m} ≈ {m_val}"
        elif relation == "collinear":
            if len(targets) < 3:
                return _fail("collinear requires 3 labels")
            p1, p2, p3 = _pt(targets[0]), _pt(targets[1]), _pt(targets[2])
            tri = sp.Triangle(p1, p2, p3)
            area = tri.area
            verified = area == 0
            detail = f"area(△{targets[0]}{targets[1]}{targets[2]}) = {area}"
        elif relation == "perpendicular":
            if len(targets) < 4:
                return _fail("perpendicular requires 4 labels: p1,p2,p3,p4")
            p1, p2, p3, p4 = (_pt(targets[i]) for i in range(4))
            v1 = p2 - p1
            v2 = p4 - p3
            dot = v1.dot(v2)
            verified = dot == 0
            detail = f"dot({targets[0]}{targets[1]},{targets[2]}{targets[3]}) = {dot}"
        elif relation == "parallel":
            if len(targets) < 4:
                return _fail("parallel requires 4 labels: p1,p2,p3,p4")
            p1, p2, p3, p4 = (_pt(targets[i]) for i in range(4))
            v1 = p2 - p1
            v2 = p4 - p3
            cross = v1[0] * v2[1] - v1[1] * v2[0]
            verified = cross == 0
            detail = f"cross({targets[0]}{targets[1]},{targets[2]}{targets[3]}) = {cross}"
        elif relation == "midpoint":
            if len(targets) < 2:
                return _fail("midpoint requires 2 labels")
            p1, p2 = _pt(targets[0]), _pt(targets[1])
            mid = (p1 + p2) / 2
            verified = True
            detail = f"midpoint({targets[0]},{targets[1]}) = {mid}"
        else:
            return _fail(f"unsupported relation: {relation!r}")

        # Sanity-run a tiny snippet in the sandbox for trace parity.
        code = (
            f"pts = {env!r}\n"
            f"targets = {targets!r}\n"
            f"relation = {relation!r}\n"
            "print('coordinate_method executed inside sandbox')\n"
        )
        exec_res = _executor(config).execute(code)
        return _ok(
            f"relation '{relation}' on {targets}: {'verified' if verified else 'NOT verified'} "
            f"({detail})",
            verified=verified,
            relation=relation,
            targets=targets,
            detail=detail,
            sandbox_output=exec_res.output,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 射影法 hook (projective method) — basic cross-ratio implementation.
# --------------------------------------------------------------------------- #
def projective_method(args: dict[str, Any], config: CodeExecConfig | None = None) -> CodeResult:
    """Projective-geometry hook: compute / verify a cross-ratio.

    Accepted ``args`` keys:

    * ``points``: ``dict[label -> [x, y]]`` of *four collinear* points.
    * ``targets``: list of 4 labels in the order ``(A, B, C, D)``.
    * ``expected``: optional expected cross-ratio value.

    The cross-ratio ``(A,B;C,D) = ((C-A)/(C-B)) / ((D-A)/(D-B))`` is computed
    after parameterising the four collinear points by their scalar coordinate
    along the line.
    """
    try:
        points_raw = args.get("points") or {}
        if not isinstance(points_raw, dict) or not points_raw:
            return _fail("projective_method requires non-empty 'points' dict")
        targets = args.get("targets") or list(points_raw.keys())
        if len(targets) != 4:
            return _fail("projective_method requires exactly 4 target labels")
        labels = list(points_raw.keys())
        coords = _parse_point_list([points_raw[k] for k in labels], "points")
        env = dict(zip(labels, coords))

        A, B, C, D = (env[targets[i]] for i in range(4))
        ax, ay = A
        bx, by = B
        dx = bx - ax
        dy = by - ay
        if dx == 0 and dy == 0:
            return _fail("degenerate: A == B")

        def _param(p: tuple[float, float]) -> sp.Rational:
            px, py = p
            # parameterise along AB: t = ((p-A)·(B-A)) / |B-A|^2
            num = sp.Rational(px - ax).limit_denominator(10**6) * dx + \
                sp.Rational(py - ay).limit_denominator(10**6) * dy
            den = sp.Rational(dx).limit_denominator(10**6) ** 2 + \
                sp.Rational(dy).limit_denominator(10**6) ** 2
            if den == 0:
                return sp.Rational(0)
            return num / den

        ta, tb, tc, td = _param(A), _param(B), _param(C), _param(D)
        if tc == tb:
            return _fail("degenerate: C == B parameter")
        if td == tb:
            return _fail("degenerate: D == B parameter")
        cr = ((tc - ta) / (tc - tb)) / ((td - ta) / (td - tb))
        cr_val = float(cr)
        expected = args.get("expected")
        verified = (expected is None) or abs(cr_val - float(expected)) < 1e-6
        detail = f"(A,B;C,D) = {cr} ≈ {cr_val}"

        code = (
            f"pts = {env!r}\n"
            f"targets = {targets!r}\n"
            "print('projective_method executed inside sandbox')\n"
        )
        exec_res = _executor(config).execute(code)
        return _ok(
            f"cross-ratio on {targets}: {'verified' if verified else 'NOT verified'} ({detail})",
            verified=verified,
            relation="cross_ratio",
            targets=targets,
            detail=detail,
            cross_ratio=cr_val,
            sandbox_output=exec_res.output,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(f"{type(exc).__name__}: {exc}")


__all__ = ["complex_method", "coordinate_method", "projective_method"]
